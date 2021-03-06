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
        if not posts.find_one({"filename": filename}):
            print("new file")
            if posts.find_one({"md5": hash}):
                print("new file and matched hash")
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
                posts.remove({"filename": filename})
                posts.insert_one(meta)
            else:
                print("new file but does not match any hash, so hard file")
                shutil.move(tmpdir+filename, basedir+filename)
                meta = {"filename": filename, "linked": "false", "md5": hash}
                posts.remove({"filename": filename})
                posts.insert_one(meta)
        # if Hard file is same with upload content
        elif posts.find_one(
                {
                    "md5": hash,
                    "linked": "false",
                    "filename": filename
                    }
                ):
            return jsonify({"stat": 'same content'})
        # Starting to process on hard file
        elif posts.find_one(
                {
                    "linked": "false",
                    "filename": filename
                    }
                ):
            # if hard file is not having linked
            # and matches other hash which is already exist
            if posts.find_one({"md5": hash}) \
                    and posts.find({"linked": filename}).count() == 0:
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
            # if hard file is not having linked files and
            # does not have any matching hash already
            elif posts.find({"linked": filename}).count() == 0 \
                    and not posts.find_one({"md5": hash}):
                print("if hard file is not having linked files \
                        and does not have any matching hash already")
                os.unlink(basedir+filename)
                shutil.move(tmpdir+filename, basedir+filename)
                meta = {"filename": filename, "linked": "false", "md5": hash}
                posts.remove({"filename": filename})
                posts.insert_one(meta)
            # if hard file has linked files and
            # matches other hash value on the db
            elif posts.find({"linked": filename}).count() > 0 \
                    and posts.find_one({"md5": hash}):
                print("hard file has links and match hash")
                src = posts.find_one({"linked": filename}, {"filename": 1})
                newparant = src['filename']
                change_parant_file(filename, newparant)
                newsrc = posts.find_one(
                        {"md5": hash, "linked": "false"}, {"filename": 1}
                        )
                newsrcfile = os.path.join(basedir, newsrc['filename'])
                os.unlink(basedir+filename)
                os.symlink(newsrcfile, basedir+filename)
                meta = {
                        "filename": filename,
                        "linked": newsrc['filename'],
                        "md5": hash
                        }
                posts.remove({"filename": filename})
                posts.insert_one(meta)
            # finaly left is hard file has linked files and
            # does not match hash of any file
            else:
                print("hard file has links and does not match hash")
                src = posts.find_one({"linked": filename}, {"filename": 1})
                newparant = src['filename']
                change_parant_file(filename, newparant)
                shutil.move(tmpdir+filename, basedir+filename)
                meta = {
                    "filename": filename,
                    "linked": "false",
                    "md5": hash
                    }
                posts.remove({"filename": filename})
                posts.insert_one(meta)
        # if soft file has same md5
        elif posts.find_one({"md5": hash, "filename": filename}):
            return jsonify({"stat": "same content"})
        # starting soft files
        elif posts.find_one({"filename": filename}) \
                and not posts.find_one({
                    "filename": filename,
                    "linked": "false"
                    }):
            print("came soft 1")
            # if new soft file matches other files hash
            if posts.find_one({"md5": hash}):
                print("came soft 2")
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
                os.unlink(basedir+filename)
                os.symlink(srcfile, basedir+filename)
                meta = {
                        "filename": filename,
                        "linked": src['filename'],
                        "md5": hash
                        }
                posts.remove({"filename": filename})
                posts.insert_one(meta)
            # if soft file does not have any match, become hard file
            else:
                print("came 3")
                os.unlink(basedir+filename)
                shutil.move(tmpdir+filename, basedir+filename)
                meta = {"filename": filename, "linked": "false", "md5": hash}
                posts.remove({"filename": filename})
                posts.insert_one(meta)
        # Default action
        else:
            print("came 4")
            shutil.move(tmpdir+filename, basedir+filename)
            meta = {"filename": filename, "linked": "false", "md5": hash}
            posts.remove({"filename": filename})
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


@app.route('/files')
@login
def list_files():
    postdb = posts.find()
    filelist = []
    for file in postdb:
        filelist.append([file['filename']])
    return jsonify({"stat": filelist})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
