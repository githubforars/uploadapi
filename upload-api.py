#!/run/current-system/sw/bin/python3.5
import os
from flask import Flask, request, redirect, url_for,\
        send_from_directory, Response, jsonify, abort
from werkzeug.utils import secure_filename
import hashlib
import pprint
import shutil
from pymongo import MongoClient
from functools import wraps
import bcrypt


client = MongoClient()
db = client.my_database
collection = db.my_collection
user = db.user
posts = db.posts
basedir = '/var/www/html/'
tmpdir = '/var/tmp/'
allowd_extn = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'nix'])
allowd_path = set([basedir, tmpdir])
app = Flask(__name__)
app.config['tmpdir'] = tmpdir


@app.route('/register', methods=['POST'])
def register():
    username = request.args.get('username', None)
    password = request.args.get('password', None)
    if request.method == 'POST':
        existing_user = user.find_one({"user": username})
        if existing_user is None:
            hashpass = bcrypt.hashpw(password.encode('utf8'), bcrypt.gensalt())
            user.insert({"username": username, "password": hashpass})
            return jsonify({"stat": "User registred"})
        else:
            return jsonify({"stat": "User already there"})
    else:
        return jsonify({"stat": "use POST instead"})


def login(f):
    @wraps(f)
    def fun_wrapper(*args, **kwargs):
        login_user = user.find_one({"username": request.args.get('username')})
        if login_user:
            if bcrypt.checkpw(request.args.get('password').encode('utf8'),
                              login_user['password']):
                return f(*args, **kwargs)
            else:
                abort(401)
        else:
            abort(401)
    return fun_wrapper


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
@login
def delete_file():
    filename = request.args.get('filename', None)
    if not posts.find_one({"filename": filename, "linked": "false"}):
        os.unlink(basedir+filename)
        posts.remove({"filename": filename})
        return jsonify({"stat": "file deleted at softlink"})
    elif filename and os.path.isfile(basedir+filename) \
            and posts.find_one({"filename": filename, "linked": "false"}) \
            and posts.find({"linked": filename}).count() == 0:
        os.unlink(basedir + filename)
        posts.remove({"filename": filename})
        return jsonify({"stat": "file deleted"})
    elif posts.find({"linked": filename}).count() > 0:
        src = posts.find_one({"linked": filename}, {"filename": 1})
        newparant = src['filename']
        change_parant_file(filename, newparant)
        os.unlink(basedir+filename)
        posts.remove({"filename": filename})
        return jsonify({"stat": "file deleted"})
    else:
        return jsonify({"stat": "filename or file is missing"})


# File upload entry point
@app.route('/upload', methods=['GET', 'POST'])
@login
def upload_file():
    file = request.files['file']
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['tmpdir'], filename))
        tmpfile = tmpdir + filename
        hash = check_hash(tmpfile)
        posts = db.posts
        src = posts.find_one(
                {
                    "linked": "false",
                    "filename": filename
                    }
                )
        if posts.find_one(
                {
                    "md5": hash,
                    "linked": "false",
                    "filename": filename
                    }
                ):
            return jsonify({"stat": 'same content'})
        elif posts.find_one(
                {
                    "linked": "false",
                    "filename": filename
                    }
                ):
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
            return jsonify({"stat": "same content"})
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
    return jsonify({"stat": "file uploaded"})


# function to download the file
@app.route('/download/<path:filename>')
@login
def send_file(filename):
    if filename and os.path.isfile(basedir+filename):
        return send_from_directory(basedir, filename, as_attachment=True)
    else:
        return jsonify({"stat": "wrong path or file does not exist"})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
