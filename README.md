picasa-batch
============

Batch uploads pictures to Picasa

## How to use:

 - Updates the picasa.batch.conf file
Create a new API
https://code.google.com/apis/console

Change the conf file with the api key and api secret.
```
api_key=<api key>
api_secret=<api secret>
```

Set the root photo folder in your filesystem
e.g.
```
rootpath=/Volumes/Photos
```
 
Run the command:
```
$ python picasa.batch.py --config picasa.batch.conf
```

It will open the browser for authentication in the first place. 
Authorize your app to have access to your personal account.

    Options
      --config CONFIG       Configuration file
      --apikey API_KEY      api key
      --apisecret API_SECRET
                            api secret
      --token TOKEN         Token returned
      --root ROOTPATH       Root Path
      --folder FOLDER [FOLDER ...]
                            Upload folder(s)
      -a                    Normalize album name
      -u                    Upload album
      -c                    Enforce create album
      -r                    Resize picture bigger than 4900px before upload (don't
                            modify the original file)
      --perms {public,private,link}
                            Album perms
