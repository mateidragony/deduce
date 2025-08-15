import os
import requests
import tarfile
import shutil
import subprocess

pages_path = './gh_pages'

index_contents = lambda v: f'''
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="description" content="Deduce is an automated proof checker meant for use in education to help students">
    <meta name="keywords" content="Deduce, Proof, Programming">
    <meta name="author" content="Jeremy Siek">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Deduce | Home</title>

    <!-- Social cards -->
    <meta property="og:url" content="https://jsiek.github.io/deduce/pages/index.html" />
    <meta property="og:type" content="website"/>
    <meta property="og:title" content="Deduce | Home" />
    <meta property="og:description" content="Deduce is an automated proof checker meant for use in education to help students" />
    <meta property="og:site_name" content="Deduce">
    <meta property="og:image" content="https://jsiek.github.io/deduce/images/logo.svg" />
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Deduce | Home">
    <meta name="twitter:description" content="Deduce is an automated proof checker meant for use in education to help students">
    <meta name="twitter:image" content="https://jsiek.github.io/deduce/images/logo.svg">

    <!-- Favicon -->
    <link rel="icon" type="image/x-icon" href="./images/logo.svg">
</head>

<body>
	<script type="text/javascript">
	 window.location.replace("./versions/{v}/index.html")
	</script>
</body>

</html>'''


def make_request(url):
    token   = os.environ['GITHUB_TOKEN']
    headers = {
        'Accept'               : 'application/vnd.github+json',
        'Authorization'        : f'Bearer {token}',
        'X-GitHub-Api-Version' : '2022-11-28'
    }
    return requests.get(url=url, headers=headers)

def generate_version(name):
    '''
    Find the deduce version pointed to by `name` in the `versions`
    directory and run the generation scripts (convert, lib_generate,
    index_generate) for the versions that support them. Then delete
    non gh_pages files and move gh_pages files to the root of the
    version directory.
    '''

    version_path = os.path.join(pages_path, 'versions', name)
    
    # v1.0 and v1.1 use /doc and /gh-pages
    old_convert    = 'doc/convert.py'
    # v1.2+ use /gh_pages/doc and /gh_pages
    convert        = 'gh_pages/doc/convert.py'
    lib_generate   = 'gh_pages/doc/lib_generate.py'
    index_generate = 'gh_pages/doc/index_generate.py'
    
    if (os.path.isfile(os.path.join(version_path, old_convert))):
        subprocess.run(['python', old_convert], cwd=version_path)
    if (os.path.isfile(os.path.join(version_path, convert))):
        subprocess.run(['python', convert], cwd=version_path)
    if (os.path.isfile(os.path.join(version_path, lib_generate))):
        subprocess.run(['python', lib_generate], cwd=version_path)
    if (os.path.isfile(os.path.join(version_path, index_generate))):
        subprocess.run(['python', index_generate], cwd=version_path)

    # delete non gh_pages
    pages_dir_name = ''
    for f in os.listdir(version_path):
        if f == 'gh_pages' or f == 'gh-pages':
            pages_dir_name = f
        else:
            path = os.path.join(version_path, f)
            if os.path.isfile(path):
                os.remove(path)
            else:
                shutil.rmtree(path)
    # extract gh_pages files from dir
    version_pages_path = os.path.join(version_path, pages_dir_name)
    for f in os.listdir(version_pages_path):
        shutil.move(os.path.join(version_pages_path, f),
                    os.path.join(version_path, f))
    os.rmdir(version_pages_path)
    
if __name__ == '__main__':
    versions_dir = os.path.join(pages_path, 'versions')
    url          = 'https://api.github.com/repos/jsiek/deduce/releases'
    versions     = make_request(url).json()
    for version in versions:
        name         = version['tag_name']
        tar          = version['tarball_url']
        tar_path     = os.path.join(pages_path, f'{name}.tar.gz')
        version_path = os.path.join(versions_dir, name)
        # get tar ball
        with open(tar_path, 'wb') as f:
            f.write(make_request(tar).content)
        # extract tar ball
        with tarfile.open(tar_path, 'r') as t:
            if not os.path.isdir(version_path):
                t.extractall(versions_dir, filter='data')
        # rename folder
        for d in os.listdir(versions_dir):
            if 'jsiek-deduce' in d:
                os.rename(os.path.join(versions_dir, d), version_path)            
        # delete tarball
        os.remove(tar_path)
        generate_version(name)
        
    # move main branch gh_pages to `main` versions folder
    excluded = ['versions', '404.html', 'versions.py']
    main_dir = os.path.join(versions_dir, 'main')
    if not os.path.isdir(main_dir):
        os.mkdir(main_dir)
    for f in os.listdir(pages_path):
        if f not in excluded:
            shutil.move(os.path.join(pages_path, f),
                        os.path.join(main_dir, f))

    # get latest version
    latest = make_request(f'{url}/latest').json()
            
    # Generate redirecting index page to latest version
    with open(os.path.join(pages_path, 'index.html'), 'w') as f:
        f.write(index_contents(latest['tag_name']))
    
