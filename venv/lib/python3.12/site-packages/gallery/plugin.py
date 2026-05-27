"""Manage a gallery of photos and videos

This is going to work as follows. It assumes you are using the ``gallery``
example to generate web-ready files and metadata and have generated all the
files you need. These are then placed somewhere web-accessible.

A program scans these to auto-generate galleries. Each gallery has its own
.gallery file which contains information about the gallery and a list of all
the filenames it contains.

.gallery files shouldn't have spaces in them and should be in their own
directory.

From these gallery files, an index page is generated along with a page for
every file so that you can browse between them. The file is named after the
file it refers to but with a ``.html`` extension.  You can also create your own
galleries.

Next steps are to:

* Have a gallery directories config option
* Place the flash files somewhere
* Build gallery index pages
* Build video pages for video files
* Wait for the conversion to finish

Start

1 16:27:39
2 16:27:42
3 16:27:42

Put a file in 3 (needs to regenerate 3/index.html)

1 16:27:39
2 16:27:42
3 16:29:45 *

Put a file in 2 (needs to regenerate 2/index.html)

1 16:27:39
2 16:30:18 *
3 16:29:45

Put a file in 1 (needs to regenerate 1/index.html)

1 16:32:14 *
2 16:30:18
3 16:29:45

The way we work is that galleries get a thumbnail, folders get an icon.

Based on this, adding a file only affects the directory it is in. When a folder timestamp is different from the index file we regenerate the index.

Now for deleting:

Start

1 16:32:14
2 16:30:18
3 16:29:45

Delete file in 3:

1 16:32:14
2 16:30:18
3 16:37:22 *

In 2::

1 16:32:14
2 16:38:00 * 
3 16:37:22

and 1:

16:38:35
16:38:00
16:37:22

With directoris: Addone in 2:

16:38:35
16:39:13 *
16:37:22

Delete one in 2:

16:38:35
16:39:46 *
16:37:22



So this all works as expected. ``ls -ca --full-time 1/2/3``


The differetn types of gallery pages generated are:

* Individual photo or video pages
* Gallery thumbnail pages
* Gallery index pages

The Gallery index pages come in two types currently:
* Those with only galleries as sub-folders
* Those without

We want to merge these so that those there is only one type of index which lists folders and galleries.

Furthermore, if a gallery has sub-galleries, or sub-folders these need to be indexed too.

So there are two types of content generated for indexes:

* Current gallery photos
* Sub-folders and galleries

There is also a new type of file called a gallery index which can specify thumbnails, title and description for a folder.
"""
import urllib
import datetime
import logging
import os.path
import re

from sitetool.template.dreamweaver import DreamweaverTemplateInstance
from sitetool.template.dreamweaver import relpath
from sitetool.api import update
from sitetool.convert.plugin import Plugin
from sitetool.exception import PluginError

log = logging.getLogger(__name__)

flash_string = """
<div align="center"><iframe src="%(path)s/flvplayer/flashvideoplayer.html?video=%(url)s&skincolor=0xCCCCFF&autoscale=false&videoheight=%(videoheight)s&videowidth=%(videowidth)s" width="%(width)s" height="%(height)s" frameborder="0" scrolling="no"></iframe></div>

<p style="text-align: right">(<a href="%(directurl)s">Download h264 movie version</a>)</p>
"""

class GalleryPlugin(Plugin):
    changed = []

    def parse_config(self, config):
        if not config:
            return None
        result = {}

        if config.has_key('PHOTO_DIRECTORY'):
            result['photo_dir'] = os.path.abspath(
                os.path.join(
                    self.site_root, 
                    config['PHOTO_DIRECTORY'].strip()
                )
            )
            #log.info(result['photo_dir'])
        if config.has_key('GALLERY_DIRECTORY'):
            result['gallery_dir'] = os.path.abspath(
                os.path.join(
                    self.site_root, 
                    config['GALLERY_DIRECTORY'].strip()
                )
            )
        if config.has_key('GALLERY_TEMPLATE'):
            result['template'] = os.path.abspath(
                os.path.join(
                    self.site_root, 
                    config['GALLERY_TEMPLATE'].strip()
                )
            )
        return result

    def on_file(self, path, page=None, template=None):
        """\
        This method generates a photo or video page for an item in a gallery
        """
        if path.startswith(os.path.join(self.config['gallery_dir'], 'flvplayer')):
            log.debug('Flash folder, ignoring')
            return False
        if not path.endswith('.gallery'):
            return False
        if not self.generated_files:
            log.debug('Skipping %r, -g not set', path)
            return False
        gen_file = path[:-len('.gallery')]+'.html' #os.path.join(os.path.split(path)[0], 'index.html')
        directory = os.path.split(path)[0]
        add_to_changed = True
        if os.path.exists(gen_file) and os.stat(directory).st_mtime > os.stat(gen_file).st_mtime:
            add_to_changed = False
        if os.path.exists(gen_file) and \
           not (os.stat(directory).st_mtime > os.stat(gen_file).st_mtime) and \
           not (os.stat(path).st_mtime > os.stat(gen_file).st_mtime) and \
           not self.force:
            log.debug('Skipping %r, not modified', path)
            return False
        # This is a file we should handle
        galleries = 0
        folders = []
        for filename in os.listdir(directory):
            if os.path.isdir(os.path.join(directory, filename)):
                folders.append(os.path.join(directory, filename))
            elif filename.endswith('gallery'):
                galleries+=1
        if galleries > 1:
            log.error(
                'More than one gallery found in %r', 
                os.path.dirname(path)
            )
            return False
        log.info('Building gallery %r', path)
        gallery = dict(parse_record(path))
        page = DreamweaverTemplateInstance(self.config['template'])
        page['doctitle'] = '<title>'+gallery['Title']+'</title>'
        page['section_navigation'] = page['section_navigation_bottom'] = '''
      <div class="nav">
      <!-- #BeginLibraryItem "%s" --><!-- #EndLibraryItem -->
      </div>
    '''%(
            relpath(
                os.path.join(
                    self.site_root, 
                    'Library', 
                    'gallery_main_nav.lbi'
                ), 
                os.path.dirname(path)
            )
        )
        page['heading'] = gallery['Title']
        links = []
        photo_filenames = gallery['photos'].split('| ')
        if not photo_filenames:
            log.error('No filenames in gallery %r', path)
            return False
        first = os.path.split(photo_filenames[0])[1]
        last = os.path.split(photo_filenames[-1])[1]
        for i, filename in enumerate(photo_filenames):
            cur = os.path.split(filename)[1]
            prev = None
            if i>0:
                prev = os.path.split(photo_filenames[i-1])[1],
            next = None
            if i<len(photo_filenames)-1:
                next = os.path.split(photo_filenames[i+1])[1],
            self.make_file(
                os.path.dirname(path), 
                filename,
                cur,
                i+1,
                len(photo_filenames),
                first,
                last,
                prev,
                next,
            )
            links.append(
                '<a href="%s"><img src="%s" alt="Photo or video" /></a>'%(
                    cur+'.html',
                    relpath(
                        os.path.join(
                            self.site_root, 
                            self.config['photo_dir'], 
                            '150', 
                            filename
                        ), 
                        os.path.dirname(path)
                    )
                )
            )
        index = ''
        if folders:
            index = self.build_index_fragment(directory)
        page['content'] = """
%s
<p>%s</p>
<p style="text-align: center">%s</p>
%s
"""     %(
            index,
            gallery['Description'],
            ' '.join(links),
            '<p class="text-right">(<a href="%s">view source</a>)</p>'%(
                os.path.split(path)[1],
            )
        )
        page.save_as_page(gen_file)
        if add_to_changed:
            self.changed.append(gen_file)
        update(
            start_path=gen_file, 
            site_root=self.site_root, 
            update_static_items=True,
        )
        return True

    def build_index_fragment(self, directory):
        """
        This method builds a directory index. It needs improving as follows:

        * If an index.galleryindex file exists, use it to build the index
        * If there are galleries as sub-directories, use them

        gallery[0].path = Name
        gallery[0].title = Name
        gallery[0].description = Name
        gallery[0].index = 
          This is a multiline string which 
          can 
              go 
           over lots of lines
        
        """
        if os.path.exists(os.path.join(directory, 'index.galleryindex')):
            raise Exception('asda')
            #galleries = parse_config(os.path.join(directory, 'index.galleryindex'))
            paths = [gallery.path for gallery in index]
            for dir in os.listdir(directory):
                if os.path.isdir(os.path.join(directory, dir)) and dir not in paths:
                    new_gallery = {'Path': dir, 'Title': dir, 'Description': '', 'Index': None}
                    galleries.append(new_gallery)
        else:
            galleries = []
            for dir in os.listdir(directory):
                if os.path.isdir(os.path.join(directory, dir)) and not \
                   os.path.join(directory, dir).startswith(os.path.join(self.config['gallery_dir'], 'flvplayer')):
                    if os.path.exists(os.path.join(directory, dir, 'index.gallery')):
                        new_gallery = dict(parse_record(os.path.join(directory, dir, 'index.gallery')))
                        new_gallery['Path'] = dir
                        galleries.append((dir, new_gallery))
                    else:
                        new_gallery = {'Path': dir, 'Title': dir, 'Description': '', 'Index': None}
                        galleries.append((dir, new_gallery))
        galleries.sort()
        galleries = [gallery[1] for gallery in galleries]
        content = ['<table>']
        for gallery in galleries:
            path = gallery['Path']
            gallery = dict(gallery)
            if not gallery['Index']:
                thumbnail = relpath(
                    os.path.join( self.site_root, self.config['gallery_dir'], 'folder.png'), 
                    directory
                )
            else: 
                thumbnail = relpath(
                    os.path.join(
                        self.site_root, 
                        self.config['photo_dir'], 
                        '150', 
                        gallery['Index']
                    ), 
                    directory
                )
            index = '<a href="%s"><img src="%s" alt="Photo or video" /></a>'%(
                os.path.join(path, 'index.html'),
                thumbnail
            )
            content.append(
                '<tr><th valign="top">%s</th><td><b>%s</b><br /><br />%s<br /><br /></td></tr>'%(
                    index, 
                    gallery['Title'],
                    gallery['Description'],
                )
            )
        content.append('</table>')
        return ''.join(content)
 
    def build_directory_index(self, directory, title=None):
        log.info('Building index %r', directory)
        if not title:
            title = 'Photos'
        page = DreamweaverTemplateInstance(self.config['template'])
        page['doctitle'] = '<title>%s</title>'%title
        page['section_navigation'] = page['section_navigation_bottom'] = '''
            <div class="nav">
            </div> '''%()
        page['heading'] = title
        page['content'] = self.build_index_fragment(directory)
        page.save_as_page(os.path.join(directory, 'index.html'))
        update(
            start_path=os.path.join(directory, 'index.html'), 
            site_root=self.site_root, 
            update_static_items=True
        )

    def on_leave_directory(self, directory):
        """
        This method builds gallery indexes
        """
        if directory.startswith(os.path.join(self.config['gallery_dir'], 'flvplayer')):
            log.debug('Flash folder, ignoring')
            return False
        if directory.startswith(self.config['gallery_dir']):
            # If the directory contains a .gallery file it shouldn't have an index
            gallery_found = False
            for filename in os.listdir(directory):
                if not os.path.isdir(filename) and filename.endswith('.gallery'):
                    gallery_found = True
                    break
            if gallery_found:
                log.debug('Skipping %r, not a gallery index directory', directory)
                return True
            # This is the photo index page.
            elif not self.generated_files:
                log.debug('Skipping gallery indexes on %r, (--auto-files not set)', directory)
                return True
            # At this point decide if ther index needs regenerating. This will need to be done if any of the child index or galleries have changed (becuase there content and indexes might have changed) or if the current diectory has changed (could be a new folder or a removed one) or if there is no index. If generating only because child ones have changed, there is no need to add to the change list
            
            regenerate = False
            add_to_changed = False   
            gal_index = os.path.join(directory, 'index.galleryindex')
            index = os.path.join(directory, 'index.html')
            if self.force:
                regenerate = True
            elif not os.path.exists(index):
                regenerate = True
            elif os.path.exists(gal_index) and os.stat(gal_index).st_mtime > os.stat(index).st_mtime:
                regenerate = True
                # It could affect the parent in this case
                add_to_changed = True
            elif os.path.exists(index) and os.stat(directory).st_mtime > os.stat(index).st_mtime:
                regenerate = True
            if not regenerate:
                for path in self.changed:
                    if os.path.split(os.path.split(path)[0])[0] == directory:
                        # One of the child paths has changed
                        regenerate = True
                        break
            if regenerate:
                self.build_directory_index(directory, os.path.split(directory)[1].replace('-', ' ').replace('_', ' ').capitalize())
            if add_to_changed:
                self.changed.append(os.path.join(directory, 'index.html'))
            return True
        return False

    def make_file(
        self, 
        directory, 
        filename, 
        link, 
        i, 
        number, 
        first, 
        last, 
        previous, 
        next
    ):
        title = link
        page = DreamweaverTemplateInstance(self.config['template'])
        page['doctitle'] = '<title>'+title+'</title>'
        if number < 2:
            last = None
            previous = None
            next = None
            first = None
        elif link == last:
            next = None
            last = None
        elif link == first:
            first = None
            previous = None
        page['section_navigation'] = page['section_navigation_bottom'] = '''
      <div class="nav">
      %s %s %d of %d %s %s
      </div>
'''%(
    first and '<a href="%s.html">&lt;&lt;</a>'%first or '&lt;&lt;',
    previous and '<a href="%s.html">&lt;</a>'%previous or '&lt;',
    i,
    number,
    next and '<a href="%s.html">&gt;</a>'%next or '&gt;',
    last and '<a href="%s.html">&gt;&gt;</a>'%last or '&gt;&gt;',
)
        page['heading'] = title
        if filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
            page['content'] = '''
                <p style="text-align: center">
                <img src="%s" alt="%s" /></p>'''%(
                relpath(
                    os.path.join(
                        self.site_root,
                        self.config['photo_dir'],
                        '1024',
                        filename
                    ), 
                    directory
                ),
                'alt',
            )
        else:
            # Need the video width and height
            meta_path = os.path.join(
                self.site_root,
                self.config['photo_dir'],
                'meta',
                filename,
            )
            print filename, meta_path
            meta = parse_record(meta_path)
            meta = dict(meta)
            if not meta.has_key('Width') or not meta.has_key('Height'):
                log.error('No video meta data for %r', meta_path)
                videowidth = 640
                videoheight = 480
            else:
                videowidth = int(meta['Width'])
                videoheight = int(meta['Height'])
            page['content'] = flash_string % {
                'videowidth': videowidth,
                'videoheight': videoheight,
                'width': videowidth+20,
                'height': videoheight+50,
                'path': relpath(
                    os.path.join(
                        self.site_root,
                        self.config['gallery_dir']
                    ), 
                    os.path.dirname(os.path.join(directory, link+'.html'))
                ),
                'url': urllib.quote(
                    relpath(
                        os.path.join(
                            self.site_root,
                            self.config['photo_dir'],
                            'h264',
                            filename
                        ), 
                        os.path.join(
                            self.site_root,
                            self.config['gallery_dir'],
                            'flvplayer',
                        ), 
                    ),
                ),
                'directurl':relpath(
                    os.path.join(
                        self.site_root,
                        self.config['photo_dir'],
                        'h264',
                        filename
                    ), 
                    os.path.join(
                        self.site_root,
                        self.config['gallery_dir'],
                        directory
                     ), 
                ),
                'still': urllib.quote(
                    relpath(
                        os.path.join(
                            self.site_root,
                            self.config['photo_dir'],
                            'still',
                            filename
                        ), 
                        os.path.join(
                            self.site_root,
                            self.config['gallery_dir'],
                            'flvplayer',
                        ), 
                    ),
                ),
            }
        path = os.path.join(
            self.site_root, 
            self.config['photo_dir'], 
            'meta', 
            filename
        )
        if os.path.exists(path):
            data = parse_record(path)
            if data:
                page['content'] += '''
                    <h2>Meta Data</h2>
                    <table>
                    %s
                    </table>
                    '''%(
                        ''.join('<tr><th>%s</th><td>%s</td></tr>'%(x[0], x[1]) for x in data)
                    )
        path = os.path.join(
            self.site_root, 
            self.config['photo_dir'],
            'exif',
            filename
        )
        if os.path.exists(path):
            data = parse_record(path)
            if data:
                page['content'] += '''
                    <h2>Exif</h2>
                    <table>
                    %s
                    </table>
                    '''%(
                        ''.join('<tr><th>%s</th><td>%s</td></tr>'%(x[0], x[1]) for x in data)
                    )
        page.save_as_page(os.path.join(directory, link+'.html'))
        self.changed.append(os.path.join(directory, link+'.html'))
        update(
            start_path=os.path.join(directory, link+'.html'), 
            site_root=self.site_root, 
            update_static_items=True
        )
        return True

def get_all_records(directory):
    records = []
    if directory.endswith('/'):
        directory = directory[:-1]
    for dirpath, dirnames, filenames in os.walk(directory):
        filenames.sort()
        for filename in filenames:
            path = os.path.join(dirpath, filename)
            records.append((path[len(directory)+1:],  parse_record(path)))
    return records

def save_record(filename, record):
    final = []
    if os.path.exists(filename):
        existing = parse_record(filename)
        # Find new records that already exist in the old records
        to_ignore = []
        for name, value in record:
            for ename, evalue in existing:
                if name.lower() == ename.lower():
                    if value == evalue:
                        to_ignore.append((name, value))
        for pair in existing:
            final.append(pair)
        for pair in record:
            if pair not in to_ignore:
                n, v = pair
                if not isinstance(n, unicode):
                    n = n.decode('utf-8')
                if not isinstance(v, unicode):
                    v = v.decode('utf-8')
                final.append((n, v))
    else:
        final = record
    max = 0
    for name, value in record:
        if len(name) > max:
            max = len(name)
    fp = open(filename, 'w')
    for name, value in final:
        row = u"%%-%ss: %%s\n"%(unicode(max))
        row = row%(name, value)
        row = row.encode('utf-8')
        fp.write(row)
    fp.close()

def parse_record(filename):
    fp = open(filename, 'r')
    data = fp.read()
    try:
        data = data.decode('utf-8')
    except:
        log.error('Could not decode %r'%filename)
        data = data.decode('utf-8', 'replace')
    lines = data.split('\n')
    fp.close()
    record = []
    for line in lines:
        if line:
            parts = line.split(':')
            name = parts[0].strip(' \t')
            value = ':'.join(parts[1:]).strip()
            if name:
                record.append((name, value))
    return record

