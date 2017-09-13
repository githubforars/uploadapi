#!/run/current-system/sw/bin/python3.5
import os
from flask import Flask, request, redirect, url_for ,send_from_directory
from werkzeug.utils import secure_filename
import hashlib
import pprint
from pymongo import MongoClient
client = MongoClient()
db = client.my_database
collection = db.my_collection
digests = []
basedir='/var/www/html/'
UPLOAD_FOLDER = '/var/www/html'
ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif','nix'])

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
@app.route('/delete', methods=['GET' , 'POST'])
def delete_file():
    filename = request.args.get('filename', None)
    print(basedir+filename)
    if filename and os.path.isfile(basedir+filename):
      os.unlink(basedir + filename)
      posts = db.posts
      posts.remove({ "filename" : filename })
      return " file deleted "
    else:
      return " filename or file is missing "

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    file = request.files['file']
    if file and allowed_file(file.filename):
       filename = secure_filename(file.filename)
       file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
       afilename = '/var/www/html/' + filename
       hasher = hashlib.md5()
       with open(afilename, 'rb') as f:
          buf = f.read()
          hasher.update(buf)
          a = hasher.hexdigest()
          digests.append(a)
          posts = db.posts
          if posts.find_one({"md5": a}):
             src=posts.find_one({"md5": a}, {"filename" : 1 })
             print(src['filename'])
             srcfile = os.path.join(basedir, src['filename'] )
             os.unlink(afilename)
             os.symlink(srcfile, afilename)
             post = {"filename": filename, "dup": "true",
             "md5": a}
             posts = db.posts
             post_id = posts.insert_one(post).inserted_id
             print('duplicate removed')
          else:
             post = {"filename": filename, "dup": "false",
             "md5": a}
             posts = db.posts
             post_id = posts.insert_one(post).inserted_id
       return redirect(url_for('upload_file',
                                filename=filename))
@app.route('/download/<path:filename>')
def send_file(filename):
    return send_from_directory('/var/www/html', filename)
if __name__ == '__main__':
    app.run(debug=True)
