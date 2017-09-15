#!/run/current-system/sw/bin/python3.5
import os
from flask import Flask, request, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
import hashlib
import pprint
import shutil
from pymongo import MongoClient
client = MongoClient()
db = client.my_database
collection = db.my_collection
posts = db.posts
digests = []
basedir = '/var/www/html/'
tmpdir = '/var/tmp/'
allowd_extn = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'nix'])
allowd_path = set([basedir, tmpdir])
app = Flask(__name__)
app.config['tmpdir'] = tmpdir


def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in allowd_extn


def check_hash(filename):
    hasher = hashlib.md5()
    with open(filename, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
        return hasher.hexdigest()


def link_to_parant(parant, src):
    os.unlink(src)
    os.symlink(parant, src)


# Will refresh the links if we thouch parant file
def change_parant_file(parant, newparant):
    os.unlink(basedir+newparant)
    shutil.copy(basedir+parant, basedir+newparant)
    if posts.find({"linked": parant}).count() > 0:
        for file in get_linked_filename_fromdb(parant):
            if not (file[0] == newparant):
                link_to_parant(basedir+newparant, basedir+file[0])
                meta = {
                        "filename": file[0],
                        "linked": newparant,
                        "md5": check_hash(basedir+file[0])
                        }
                posts.remove({"filename": file[0]})
                posts.insert_one(meta)
    meta = {
            "filename": newparant,
            "md5": check_hash(basedir+newparant),
            "linked": "false"
            }
    posts.remove({"filename": newparant})
    posts.insert_one(meta)


# To get the all the files which has been linked to a file
def get_linked_filename_fromdb(parant):
    symlink_list = []
    for i in posts.find({"linked": parant}, {"filename": 1}):
        symlink_list.append([i['filename']])
    return symlink_list


# delete endpoint
@app.route('/delete', methods=['GET', 'POST'])
def delete_file():
    filename = request.args.get('filename', None)
    if not posts.find_one({"filename": filename, "linked": "false"}):
        os.unlink(basedir+filename)
        posts.remove({"filename": filename})
        return ''' file deleted at softlink'''
    elif filename and os.path.isfile(basedir+filename) \
            and posts.find_one({"filename": filename, "linked": "false"}) \
            and posts.find({"linked": filename}).count() == 0:
        os.unlink(basedir + filename)
        posts.remove({"filename": filename})
        return ''' file deleted '''
    elif posts.find({"linked": filename}).count() > 0:
        print("other place")
        src = posts.find_one({"linked": filename}, {"filename": 1})
        newparant = src['filename']
        change_parant_file(filename, newparant)
        os.unlink(basedir+filename)
        posts.remove({"filename": filename})
        return ''' file deleted at hardlink'''
    else:
        return ''' filename or file is missing '''


# File upload entry point
@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    file = request.files['file']
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['tmpdir'], filename))
        tmpfile = tmpdir + filename
        hash = check_hash(tmpfile)
        posts = db.posts
        src = posts.find_one({"linked": "false", "filename": filename})
        if posts.find_one(
                {"md5": hash, "linked": "false", "filename": filename}
                ):
            print('same content')
        elif posts.find_one({"linked": "false", "filename": filename}):
            if posts.find_one({"md5": hash}):
                src = posts.find_one(
                        {"md5": hash, "linked": "false"}, {"filename": 1}
                        )
                srcfile = os.path.join(basedir, src['filename'])
                os.unlink(basedir+filename)
                os.symlink(srcfile, basedir+filename)
                meta = {
                        "filename": filename,
                        "linked": src['filename'],
                        "md5": hash
                        }
                posts.remove({"filename": filename})
                posts.insert_one(meta)
            elif posts.find({"linked": filename}).count() == 0:
                os.unlink(basedir+filename)
                shutil.move(tmpdir+filename, basedir+filename)
                meta = {"filename": filename, "linked": "false", "md5": hash}
                posts.remove({"filename": filename})
                posts.insert_one(meta)
            else:
                src = posts.find_one({"linked": filename}, {"filename": 1})
                newparant = src['filename']
                change_parant_file(filename, newparant)
                shutil.move(tmpdir+filename, basedir+filename)
        elif posts.find_one({"md5": hash, "filename": filename}):
            print("same content")
        elif posts.find_one({"filename": filename}):
            os.unlink(basedir+filename)
            shutil.move(tmpdir+filename, basedir+filename)
            meta = {"filename": filename, "linked": "false", "md5": hash}
            posts.remove({"filename": filename})
            posts.insert_one(meta)
        elif posts.find_one({"md5": hash}):
            src = posts.find_one(
                    {
                        "md5": hash,
                        "linked": "false"
                        },
                    {
                        "filename": 1
                        }
                    )
            srcfile = os.path.join(basedir, src['filename'])
            os.symlink(srcfile, basedir+filename)
            meta = {
                    "filename": filename,
                    "linked": src['filename'],
                    "md5": hash
                    }
            posts.insert_one(meta)
        else:
            shutil.move(tmpdir+filename, basedir+filename)
            meta = {"filename": filename, "linked": "false", "md5": hash}
            posts.insert_one(meta)
    return redirect(url_for('send_file',
                    filename=filename))


# To get the file download entry point
@app.route('/download/<path:filename>')
def send_file(filename):
    if filename and os.path.isfile(basedir+filename):
        return send_from_directory(basedir, filename, as_attachment=True)
    else:
        return ''' wrong path or file does not exist '''
if __name__ == '__main__':
    app.run(debug=True, port=5000)
