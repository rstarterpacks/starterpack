from __future__ import print_function
import ast
import io
import os
import praw
import subprocess


class Reddit(praw.Reddit):
    def login(self, username, password, client_id, client_secret):
        self.clear_authentication()
        self.set_oauth_app_info(client_id, client_secret, '')
        self.config.user = username
        self.config.pswd = password
        self.config.grant_type = 'password'
        self.config.api_request_delay = 1.0
        self.get_access_information('code')
        self.user = self.get_me() # praw has a bug


def deploy_images(diff, reddit, force=False):
    global open
    oopen = open
    def open(name, *a, **kw):
        try:
            return oopen(name, *a, **kw)
        except FileNotFoundError:
            b = io.BytesIO(b'Noexist')
            b.name = name
            return b
    if force:
        force_info = set((i['name'], os.path.splitext(i['url'])[1]) for i in
                         reddit.get_stylesheet(os.getenv('subreddit')
                             )['images'])
        force_info = ["{0}{1}".format(k, v) for k, v in force_info]
        push = os.listdir(os.getenv('imgdir', 'images'))
        remove = [x for x in force_info if x not in push]
        diff = {os.path.join(os.getenv('imgdir', 'images'), a): True
                for a in push}
        diff.update({b: False for b in remove})
    else:
        diff = {f: os.path.isfile(f) for f in diff}
    deploy_data = {'subreddit': os.getenv('subreddit')}
    for image, exists in diff.items():
        data = dict(deploy_data)
        with open(image) as image_file:
            if exists:
                data['image_path'] = image
            else:
                data['name'] = os.path.splitext(
                    os.path.basename(image_file.name)
                )[0]
            getattr(
                reddit,
                "{0}_image".format("upload" if exists else "delete")
            )(**data)


def deploy(force=ast.literal_eval(os.getenv('force_deploy', 'False'))):
    stylesheet = os.getenv('cssfile', 'stylesheet.css')
    imgdir = os.getenv('imgdir', 'images')
    diff = subprocess.check_output(['git', 'diff',
                                    '--name-only', 'HEAD^'])
    diff = diff.split() if isinstance(diff, str) else \
        diff.decode('utf-8').split()
    update_css = stylesheet in diff
    image_diff = {f: os.path.isfile(f)
                  for f in diff if f.startswith(imgdir + '/')}
    update_images = bool(image_diff.keys())
    r = Reddit(
        os.getenv("UASTRING", "Automatic CSS Deployment for starterpack")
    )
    r.login(
        os.getenv('username'),
        os.getenv('password'),
        os.getenv('client_id'),
        os.getenv('client_secret'),
    )
    if update_images or force:
        deploy_images(image_diff, r, force)
    if update_css or force:
        with open(stylesheet, 'r') as css:
            r.set_stylesheet(os.getenv('subreddit'), css.read())

if __name__ == '__main__':
    deploy()