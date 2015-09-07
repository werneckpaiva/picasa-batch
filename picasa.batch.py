#!/usr/bin/python

import sys
import string, re, time
from datetime import datetime
import ConfigParser
import os, signal
import hashlib
from PIL import Image
from PIL.ExifTags import TAGS
from tempfile import mkstemp

import argparse

from oauth2client.file import Storage
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.tools import run_flow
import atom

import gdata.photos.service, gdata.media, gdata.geo, gdata.gauth
import httplib2


class PicasaClient():

    api_key = None
    api_secret = None
    token = None

    gdClient = None

    rootpath=None

    verbose=False

    forceCreateAlbum=False
    forceResizePhoto=False

    perm=None

    albuns=None

    PICASA_MAX_FREE_DIMENSION = 4900

    #pattern = re.compile('\.(jpg|avi)$', re.IGNORECASE)
    pattern = re.compile('\.jpg$', re.IGNORECASE)
    patternWrong = re.compile('^\.', re.IGNORECASE)

    def load_stored_credentials(self):
        storage = Storage("credentials")
        value = storage.get()
        if not value:
            raise Exception("Invalid token")
        self.credentials = value

    def save_credentials(self):
        storage = Storage("credentials.dat")
        storage.put(self.credentials)

    def refresh_token(self):
        self.credentials.refresh(httplib2.Http())

    def connect(self):
        flow = OAuth2WebServerFlow(client_id=self.api_key,
                           client_secret=self.api_secret,
                           scope='https://picasaweb.google.com/data/',
                           redirect_uri='http://localhost/return',
                           access_type='offline', approval_prompt='force')
        if self.token:
            self.credentials = flow.step2_exchange(self.token)
            self.save_credentials()
        else:
            storage = Storage("credentials.dat")
            credentials = storage.get()
            if not credentials:
                class MyOpts:
                    pass
                flags=MyOpts()
                flags.logging_level = 'DEBUG'
                flags.noauth_local_webserver = False
                flags.auth_host_port = [8100]
                flags.auth_host_name = 'localhost'
                credentials = run_flow(flow, storage, flags=flags)
            if credentials.access_token_expired:
                self.refresh_token()
            self.credentials = credentials
        
#         auth2token = gdata.gauth.OAuth2TokenFromCredentials(credentials)
        self.gdClient = gdata.photos.service.PhotosService(additional_headers={'Authorization' : 'Bearer %s' % self.credentials.access_token})
#         self.gdClient = auth2token.authorize(gdClient)

        self.load_user_profile()


    def load_user_profile(self):
        print "Loading user profile"
        result = self.gdClient.GetUserFeed()
        self.userid = result.user.text
        self.gdClient = gdata.photos.service.PhotosService(email=self.userid, additional_headers={'Authorization' : 'Bearer %s' % self.credentials.access_token})

    def batchUpload(self, paths):
        self.connect()
        if (self.verbose): print "Batch upload: "
        for path in paths:
            self.batchUploadPath(path)

    def batchUploadPath(self, path):

        # Get a list of files
        files = []
        dirs = []
        for filename in os.listdir(path):
            if self.patternWrong.search(filename):
                continue
            file = os.path.join(path, filename)
            if os.path.isfile(file):
                if self.pattern.search(file):
                    files.append(filename)
            elif os.path.isdir(file):
                dirs.append(file)
        files.sort()
        dirs.sort()

        if len(files) > 0:
            albumName=self.transformPath2Album(path)
            file = os.path.join(path, files[0])
            albumDate = self.getAlbumDateFromPhotos(file)
            # if the album doesn't exist, create one
            album = None
            if (not self.forceCreateAlbum):
                # print "Dont enforce create Album: "
                album=self.getAlbum(albumName)
            if album is None:
                if (self.verbose): print "Creating Album: " + albumName
                album=self.createAlbum(albumName, albumDate)
            else:
                if (self.verbose): print "Album: %s " % (albumName)
                album.timestamp = gdata.photos.Timestamp(text=albumDate)
                # self.gdClient.Put(album, album.GetEditLink().href, converter=gdata.photos.AlbumEntryFromString)
            photoList = self.getPhotosFromAlbum(album)
        noUploads=False
        for filename in files:
            file = os.path.join(path, filename)
            # was the file already uploaded
            md5=md5sum(file)
            if (self.isPhotoInAlbum(md5, photoList)):
                sys.stdout.write(".")
                noUploads=True
                continue
            if noUploads: print ""; noUploads=False
            if self.forceResizePhoto:
                self.resizeAndUploadPhoto(file, filename, md5, album)
            else:
                self.uploadPhoto(file, filename, md5, album);
            
        if noUploads: print ""; 
        for dir in dirs:
            self.batchUploadPath(dir)

    def transformPath2Album(self, fullpath):
        path = fullpath.strip()    
        path = re.sub('/$', '', path)
        path = re.sub(self.rootpath, '', fullpath)
        path = re.sub('/[0-9]+_', '/', path)
        path = re.sub('_', ' ', path)
        path = re.sub('^/ *', '', path)
        path = re.sub('/ *$', '', path)
        path = re.sub('/', ' / ', path)
        return path

    def transformFilename2PhotoTitle(self, filename):        
        title = self.pattern.sub('', filename)
        title = re.sub('_', ' ', title)
        return title
        
    def transformPhotoTitle2Tags(self, photoTitle):        
        tags = re.sub(' +[0-9]+$', '', photoTitle)
        tags = re.sub(' ', ',', tags);
        return tags
    
    def getAlbum(self, albumName):
        if self.albuns is None:
            self.albuns = self.getAlbums()
        for album in self.albuns:
            if album.title.text.strip() == albumName.strip():
                return album
        return None
        
    def getPhotosFromAlbum(self, album):
        photos = self.gdClient.GetFeed('/data/feed/api/user/%s/albumid/%s?kind=photo' % (self.userid, album.gphoto_id.text))
        return photos.entry
     
    def createAlbum(self, albumName, albumDate):
        while True:
           try:
               album = self.gdClient.InsertAlbum(albumName, albumName, access=self.perm, timestamp=albumDate)
               return album
           except Exception as e:
               print "Create failed."
               time.sleep(2)
    
    def getAlbums(self):
        uri = '/data/feed/api/user/%s?kind=album' % (self.userid)
        albums=[]
        limit = 500
        offset = 1
        while True:
            albumsBlock=self.gdClient.GetFeed(uri, limit=limit, start_index=offset)
            total = int(albumsBlock.total_results.text)
            offset = len(albums) + limit
            albums.extend(albumsBlock.entry)
            # print 'Getting albums: %s' % (len(albums))
            if len(albumsBlock.entry)<=1 or offset >= total:
               break
        return albums

    def getAlbumDateFromPhotos(self, file):
        try:
            img = Image.open(file)
            exif = img._getexif()
        except:
            statinfo = os.stat(file)
            dt = '%i' % int(statinfo.st_mtime * 1000)
            return dt
        if exif != None:
            for tag, value in exif.items():
               decoded = TAGS.get(tag, tag)
               if decoded == 'DateTime':
                   try:
                       dt = '%i' % int(time.mktime(time.strptime(value, "%Y:%m:%d %H:%M:%S"))  * 1000)
                       return dt
                   except ValueError:
                       return None
        statinfo = os.stat(file)
        dt = '%i' % int(statinfo.st_mtime * 1000)
        return dt

    def isPhotoInAlbum(self, md5, photoList):
        for photo in photoList:
            if photo.checksum.text==md5:
                return True
        return False

    def uploadPhoto(self, file, filename, md5, album):
        photoTitle = self.transformFilename2PhotoTitle(filename)
        tags = self.transformPhotoTitle2Tags(photoTitle)
        entry = gdata.photos.PhotoEntry()
        entry.title = atom.Title(text=photoTitle)
        entry.summary = atom.Summary(text=photoTitle, summary_type='text')
        entry.checksum = gdata.photos.Checksum(text=md5)
        entry.media.keywords = gdata.media.Keywords()
        entry.media.keywords.text = tags
        if (self.verbose): print '%s [%s]' % (filename, photoTitle);
        uploaded=False
        while uploaded == False:
            try:
               self.gdClient.InsertPhoto('/data/feed/api/user/default/albumid/%s' % (album.gphoto_id.text), entry, file, content_type='image/jpeg')
               uploaded=True
            except gdata.photos.service.GooglePhotosException as e:
                print "Upload failed. ", e 
                self.refresh_token()
                time.sleep(2)

    def resizeAndUploadPhoto(self, file, filename, md5, album):
        try:
            img = Image.open(file)
            (width, height) = img.size
            newDimension = None
            ratio = float(width) / float(height)
            if width > height and width > self.PICASA_MAX_FREE_DIMENSION:
                newHeight = int(self.PICASA_MAX_FREE_DIMENSION / ratio)
                newDimension = (self.PICASA_MAX_FREE_DIMENSION, newHeight)

            elif height > width and height > self.PICASA_MAX_FREE_DIMENSION:
                newWidth = int(self.PICASA_MAX_FREE_DIMENSION * ratio)
                newDimension = (newWidth, self.PICASA_MAX_FREE_DIMENSION)

            # Create a temporary resized file 
            if newDimension is not None:
                print "Resizing %s (%s, %s) to (%s, %s)" % (filename, width, height, newDimension[0], newDimension[1])

                resizedImage = img.resize(newDimension) 
                tempFile, tempPath = mkstemp()

                resizedImage.save(tempPath, "JPEG", exif=img.info['exif'])
                self.uploadPhoto(tempPath, filename, md5, album)
                os.close(tempFile)
                os.remove(tempPath)
            else:
                self.uploadPhoto(file, filename, md5, album)
        except Exception as e:
            print "Unable to open file %s" % filename
            import traceback; traceback.print_exc()

    def normalizeAlbums(self):
        self.connect()
        self.albuns = self.getAlbums()
        for album in self.albuns:
            newTitle = album.title.text.strip()
            newTitle = re.sub('^/ *', '', newTitle)
            newTitle = re.sub('/ *$', '', newTitle)
            print "'%s' -> '%s'" % (album.title.text, newTitle)
            album.title.text=newTitle
            self.gdClient.Put(album, album.GetEditLink().href, converter=gdata.photos.AlbumEntryFromString)
            print "normalize"


def md5sum(fileName):
    m = hashlib.md5()
    try:
        fd = open(fileName,"rb")
    except IOError:
        print "Unable to open the file in readmode: " + fileName
        return
    content = fd.readlines()
    fd.close()
    for eachLine in content:
        m.update(eachLine)
    return m.hexdigest()


def readFromConfigFile(client, args):
    configParser = ConfigParser.ConfigParser()
    configParser.readfp(args.config)
    client.api_key = getParam(args.api_key, configParser, 'api_key');
    client.api_secret = getParam(args.api_secret, configParser, 'api_secret');
    client.rootpath = getParam(args.rootpath, configParser, 'rootpath');
    client.perm = args.perm
    client.verbose = args.verbose
    client.forceCreateAlbum = args.forceCreateAlbum
    client.forceResizePhoto = args.forceResizePhoto
    client.token = args.token


def getParam(arg, parser, item):
    if arg is not None:
        return arg
    return parser.get('config', item);


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', dest='verbose', help='Verbose', action='store_true')
    parser.add_argument('--config', dest='config', help='Configuration file', type=argparse.FileType('r'))
    parser.add_argument('--apikey', dest='api_key', help='api key')
    parser.add_argument('--apisecret', dest='api_secret', help='api secret')
    parser.add_argument('--token', dest='token', help='Token returned')
    parser.add_argument('--root', dest='rootpath', help='Root Path')
    parser.add_argument('--folder', dest="folder", help='Upload folder(s)', nargs='+', action='store')
    parser.add_argument('-a', dest='normalizeAlbum', help='Normalize album name', action='store_true')
    parser.add_argument('-u', dest='upload', help='Upload album', action='store_true')
    parser.add_argument('-c', dest="forceCreateAlbum", help='Enforce create album', action='store_true')
    parser.add_argument('-r', dest="forceResizePhoto", help='Resize picture bigger than 4900px before upload (don\'t modify the original file)', action='store_true')
    parser.add_argument('--perms', dest='perm', action='store', help='Album perms', choices=['public', 'private', 'link'], default='private')
    args = parser.parse_args()
    client = PicasaClient();
    if args.config:
        readFromConfigFile(client, args)
    if args.perm==True:
        pass
    elif args.upload==True:
        client.batchUpload(args.folder)
    elif args.normalizeAlbum==True:
        client.normalizeAlbums()


def trapCtrlC():
   def terminateSignalHandler(signal, frame):
      sys.exit()
   signal.signal(signal.SIGINT, terminateSignalHandler)


trapCtrlC()

if __name__ == "__main__":
    main()
