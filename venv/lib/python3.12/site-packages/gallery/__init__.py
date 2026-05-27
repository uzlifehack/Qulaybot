"""Tools for converting photos and videos for use on the web

::

    $ python -m gallery --help

"""

import os.path
import logging
import sys
import getopt
import subprocess
import math

from bn import uniform_path
from bn import relpath
from commandtool import parse_html_config
from commandtool import strip_docstring
from commandtool import option_names_from_option_list
from commandtool import set_error_on
from commandtool import parse_command_line
from commandtool import handle_program
from commandtool import makeHandler

from gallery.plugin import save_record, get_all_records
from gallery import help_strings

log = logging.getLogger(__name__)

#
# Command Handlers
#

def handle_command_gallery(
    option_sets, 
    command_options, 
    args
):
    """\
    usage: ``%(program)s [PROGRAM_OPTIONS] gallery META DEST``

    Automatically build galleries based on the file strucutre of the ``meta`` 
    directory specified as ``META`` and put them in ``DEST``. It needs the 
    ``h264`` and ``1024`` directoires too to create the create links.

    The order of files is a gallery is determined by stripping all characters 
    which aren't numbers from the filename and then numbering the files in order

    Arguments:

      :``META``: The path to the photo and video metadata directory
      :``DEST``: An empty directory within which the galleries will be placed

      All ``PROGRAM_OPTIONS`` (see \`%(program)s --help')
    """
    if not len(args):
        raise getopt.GetoptError('No META directory specified')
    elif len(args)<2:
        raise getopt.GetoptError('No DEST specified')
    elif len(args)>2:
        raise getopt.GetoptError('Got unexpected argument %r'%args[2])
    if not os.path.exists(args[0]):
        raise getopt.GetoptError('No such directory %r'%args[0])
    if not os.path.exists(args[1]):
        raise getopt.GetoptError('No such directory %r'%args[1])
    run(os.path.normpath(os.path.abspath(args[1])), os.path.normpath(os.path.abspath(args[0])))

def handle_command_thumb(
    option_sets, 
    command_options, 
    args
):
    """\
    usage: ``%(program)s [PROGRAM_OPTIONS] thumb SOURCE DEST``

    Recursively convert all the pictures and videos in SOURCE into a directory
    structure in DEST

    Arguments:

      :``SOURCE``: The source directory for the images and videos
      :``DEST``: An empty directory which will be populated with a converted data
                 structure

    Options:
      -t, --thumbnail-size=THUMBNAIL_SIZE    The width in pixels of the thumbnails
      -y, --video-overlay-file=OVERLAY_FILE  A transparent PNG file the same size 
                                             as the thumbnails to overlay on video
                                             thumbnails to distinguish them from  
                                             picture thumbnails
      --gallery-exif                         Generate EXIF data files  
      --gallery-stills                       Generate video stills
      --gallery-reduced                      Generate reduced size photos 
                                             (1024x1024 max)
      --gallery-thumb                        Generate thumbnails from video stills 
                                             and reduced sized photos (150x150) and
                                             apply the video overlay to the video 
                                             thubnails
      --gallery-h264                         Generate copressed and resized h264
                                             video for use in flash players

      All ``PROGRAM_OPTIONS`` (see \`%(program)s --help')
    """
    if not len(args):
        raise getopt.GetoptError('No SOURCE specified')
    elif len(args)<2:
        raise getopt.GetoptError('No DEST specified')
    elif len(args)>2:
        raise getopt.GetoptError('Got unexpected argument %r'%args[2])
    internal_vars = set_error_on(
        command_options, 
        allowed=[
            'video_overlay_file',
            'gallery_thumb',
            'gallery_reduced',
            'gallery_exif',
            'gallery_h264',
            'gallery_meta',
            'gallery_still',
        ],
    )
    if not os.path.exists(args[0]):
        raise getopt.GetoptError('No such directory %r'%args[0])
    if not os.path.exists(args[1]):
        os.mkdir(args[1])
    #elif os.listdir(args[1]):
    #    raise getopt.GetoptError('DEST %r is not empty'%args[1])
    source = os.path.normpath(os.path.abspath(args[0]))
    dest = os.path.normpath(os.path.abspath(args[1]))
    overlay = internal_vars.get('video_overlay_file', None)
    if overlay and not os.path.exists(overlay):
        raise getopt.GetoptError('No such file %r for video overlay'%overlay)
    force = False
    if internal_vars.has_key('gallery_still'):
        log.info(
            "Making video stills"
        )
    if internal_vars.has_key('gallery_thumb'):
        if internal_vars.has_key('gallery_still') and \
           internal_vars.has_key('gallery_reduced'):
            log.info(
                "Making image and video thumbnails"
            )
        elif internal_vars.has_key('gallery_still'):
            log.info(
                "Making video thumbnails"
            )
        elif internal_vars.has_key('gallery_reduced'):
            log.info(
                "Making image thumbnails"
            )
    if internal_vars.has_key('gallery_reduced'):
        log.info(
            "Making reduced images"
        )
    if internal_vars.has_key('gallery_meta'):
        log.info(
            "Making meta files"
        )
    if internal_vars.has_key('gallery_exif'):
        log.info(
            "Extracting EXIF data"
        )
    if internal_vars.has_key('gallery_h264'):
        log.info(
            "Making h264 videos"
        )
    log.info('Making directories...')
    make_dirs(source, dest)
    log.info('Starting... (this could take ages, use -v option for output)')

    cur_dirpath = None
    for dirpath, dirnames, filenames in os.walk(source):
        if dirpath != cur_dirpath:
            log.info('Working in %r'%dirpath)
            cur_dirpath = dirpath
        for filename in filenames:
            if filename.startswith('.'):
                log.debug('Ignoring hidden file %r', filename)
                continue
            path = os.path.join(dirpath, filename)
            if internal_vars.has_key('gallery_meta') and not os.path.exists(os.path.join(dest, 'meta', path[len(source)+1:])):
                dst = os.path.join(dest, 'meta', path[len(source)+1:])
                fp = open(dst, 'w')
                fp.write('')
                fp.close()
            if filename.split('.')[-1].lower() in [
                'cr2', 
                'png', 
                'jpg', 
                'jpeg'
            ]:
                if internal_vars.has_key('gallery_reduced'):
                    dst = os.path.join(dest, '1024', path[len(source)+1:])
                    if force or (not os.path.exists(dst)) or \
                       not os.stat(dst).st_size or \
                       (os.stat(source)[8] > os.stat(dst)[8]):
                        log.debug("Converting %r to %r"%(path, dst))

                        # It is a picture, find its orientation
                        p = subprocess.Popen("exiv2 pr -Pnv".split(" ")+[path], shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        so, se = p.communicate()
                        or_ = 0
                        orientation = None
                        for line in so.split('\n'):
                            if "Orientation" in line:
                                or_ = int(line.strip()[-1])
                                if or_ > 8 or or_ < 1:
                                    log.error('Orientation of %r for %r', or_, source)
                                else:
                                    orientation = orientation_types[or_]
                                log.debug("Orientation1: %s, %s, %s", path, or_, orientation)
                                break
                        if orientation is None:
                            log.error('Could not find orientation for %r, %s', path, so)
                        p.wait()
                        cmd = [
                            "convert",
                            #"-auto-orient",
                            "-thumbnail",
                            "1024x1024>", 
                            "-unsharp", 
                            "0x.5",
                        ]
                        if orientation:
                            cmd += orientation
                        src = path[:]
                        if src.lower().endswith('.cr2'):
                            # Assume cannon raw format:
                            src='cr2:'+src
                        dst='jpg:'+dst
                        cmd = cmd+[src, dst]
                        process = subprocess.Popen(
                            cmd,
                            shell=False,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE
                        )
                        retcode = process.wait()
                        out, err = process.communicate()
                        if retcode != 0:
                            log.warning("Failed to create 1024 for %r", path)
                            log.warning('cmd: %s', ' '.join(cmd))
                            log.warning('out: %s', out)
                            log.warning('err: %s', err)
                if internal_vars.has_key('gallery_thumb'):
                    # Try to use the smaller file if it is available
                    source_1024 = os.path.join(
                        dest, 
                        '1024', 
                        path[len(source)+1:]
                    )
                    dst = os.path.join(dest, '150', path[len(source)+1:])
                       # XXX Should this be path?
                    if force or (not os.path.exists(dst)) or \
                       not os.stat(dst).st_size or \
                       (os.stat(source)[8] > os.stat(dst)[8]):
                        if not os.path.exists(source_1024):
                            source_1024 = path
                            if path.lower().endswith('.cr2'):
                                # Assume cannon raw format:
                                source_1024='cr2:'+path
                        else:
                            source_1024 = 'jpg:'+source_1024
                        dst='jpg:'+dst
                        log.debug("Converting %r to %r"%(source_1024, dst))
                        cmd = [
                            "convert", 
                            "-thumbnail", "x300",
                            "-resize", '300x<',
                            "-resize", '50%',
                            "-gravity", "center", 
                            "-crop", "150x150+0+0", 
                            "+repage", 
                            "-unsharp", "0x.5",
                        ]
                        cmd += [
                            source_1024, 
                            dst,
                        ]
                        process = subprocess.Popen(
                            cmd, 
                            shell=False, 
                            stdout=subprocess.PIPE, 
                            stderr=subprocess.PIPE
                        )
                        retcode = process.wait()
                        out, err = process.communicate()
                        if retcode != 0:
                            log.warning(
                                "Failed to create 150 for %r", 
                                source_1024
                            )
                            log.warning('cmd: %s', ' '.join(cmd))
                            log.warning('out: %s', out)
                            log.warning('err: %s', err)
            if internal_vars.has_key('gallery_exif') and \
               filename.split('.')[-1].lower() in ['jpg', 'jpeg']:
                dst = os.path.join(dest, 'exif', path[len(source)+1:])
                if force or (not os.path.exists(dst)) or \
                   not os.stat(dst).st_size or \
                   (os.stat(source)[8] > os.stat(dst)[8]):
                    log.debug("Extracting %r to %r"%(path, dst))
                    cmd = "exiv2 pr".split(' ')+[path]
                    process = subprocess.Popen(
                        cmd, 
                        shell=False, 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE
                    )
                    out, err = process.communicate()
                    retcode = process.wait()
                    if retcode != 0:
                        if 'Warning: JPEG format error, rc = 5' in err or \
                           'No Exif data found in the file' in err:
                            # Can't do much about these, no big deal though
                            fp = open(dst, 'w')
                            fp.write(out)
                            fp.close()
                        else:
                            log.warning("Failed to extract EXIF for %r", path)
                            log.warning('cmd: %s', ' '.join(cmd))
                            log.warning('out: %s', out)
                            log.warning('err: %s', err)
                    else:
                        fp = open(dst, 'w')
                        fp.write(out)
                        fp.close()
            if filename.split('.')[-1].lower() in [
                'mpeg',
                'wmv',
                '3gp',
                'mov',
                'mp4',
                'mpg',
                'avi'
            ]:
                if internal_vars.has_key('gallery_still'):
                    dst = os.path.join(
                        dest, 
                        'still', 
                        path[len(source)+1:],
                    )
                    if force or (not os.path.exists(dst)) or \
                       not os.stat(dst).st_size or \
                       (os.stat(source)[8] > os.stat(dst)[8]):
                        log.debug("Converting %r to %r"%(path, dst))
                        cmd = [
                            "ffmpeg", 
                            "-i", path,
                            "-an",
                            "-ss", "00:00:02.5",
                            "-r", "1",
                            "-vframes", "1",
                            "-f", "image2",
                            "-y",
                            dst,
                        ]
                        process = subprocess.Popen(
                            cmd, 
                            shell=False, 
                            stdout=subprocess.PIPE, 
                            stderr=subprocess.PIPE
                        )
                        retcode = process.wait()
                        out, err = process.communicate()
                        worked = False
                        if err or retcode != 0:
                            log.warning("Failed to extract still from %r, trying at 0 secs", path)
                            cmd = [
                                "ffmpeg", 
                                "-i", path,
                                "-an",
                                "-r", "1",
                                "-vframes", "1",
                                "-f", "image2",
                                "-y",
                                dst,
                            ]
                            process = subprocess.Popen(
                                cmd, 
                                shell=False, 
                                stdout=subprocess.PIPE, 
                                stderr=subprocess.PIPE
                            )
                            retcode = process.wait()
                            out, err = process.communicate()
                            if retcode != 0:
                                log.warning("Failed to extract still from for %r", path)
                                log.warning('cmd: %s', ' '.join(cmd))
                                log.warning('out: %s', out)
                                log.warning('err: %s', err)
                            else:
                                worked = True
                        else:
                            worked = True
                        if worked:
                            process = subprocess.Popen(['exiv2', '-ps', dst], shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            stdout, stderr = process.communicate()
                            retcode = process.wait()
                            width = None
                            height = None
                            found = False
                            for line in stdout.split('\n'):
                                if 'Image size' in line:
                                    width, height = line.split(':')[-1].strip().split(' x ')
                                    found = True
                            if not found:
                                log.error("Failed %r", path)
                            else:
                                save_record(os.path.join(dest, 'exif', path[len(source)+1:]), {'Width': str(width), 'Height': str(height)}.items())
                                ratio = int(width)/float(height)
                                scaled_height = math.sqrt((640*480)/ratio)
                                scaled_width = int(ratio*scaled_height)
                                scaled_height = int(scaled_height)
                                save_record(os.path.join(dest, 'meta', path[len(source)+1:]), {'Width': str(scaled_width), 'Height': str(scaled_height)}.items())
                                log.info("Added exif and meta for %s width: %s, height: %s", path[len(source)+1:], scaled_width, scaled_height)
                if internal_vars.has_key('gallery_thumb'):
                    source_still = os.path.join(
                        dest, 
                        'still', 
                        path[len(source)+1:]
                    )
                    dst = os.path.join(
                        dest,
                        '150', 
                        path[len(source)+1:]
                    )
                    if force or (not os.path.exists(dst)) or \
                       not os.stat(dst).st_size or \
                       (os.stat(source)[8] > os.stat(dst)[8]):
                        if not os.path.exists(source_still):
                            log.warning(
                                'No extracted still found for %r',
                                path,
                            )
                        else:
                            log.debug(
                                "Converting %r to %r", 
                                source_still, 
                                dst,
                            )
                            cmd = [
                                "convert",
                                "-auto-orient",
                                "-thumbnail", "x150",
                                "-crop", "150x150+0+0",
                                "+repage",
                                "-gravity", "center",
                                "-unsharp", "0x.5",
                            ]
                            if overlay:
                                cmd = cmd+[
                                    'jpg:'+source_still, 
                                    '-draw', "image over 0,0 150,150 '%s'"%overlay,
                                    'jpg:'+dst,
                                ]
                            else: 
                                cmd = cmd+['jpg:'+source_still, 'jpg:'+dst]
                            process = subprocess.Popen(
                                cmd, 
                                shell=False, 
                                stdout=subprocess.PIPE, 
                                stderr=subprocess.PIPE,
                            )
                            retcode = process.wait()
                            out, err = process.communicate()
                            if retcode != 0:
                                log.warning(
                                    "Failed to create thumbnail from still %r", 
                                    source_still
                                )
                                log.warning('cmd: %s', ' '.join(cmd))
                                log.warning('out: %s', out)
                                log.warning('err: %s', err)
                if internal_vars.has_key('gallery_h264'):
                    dst = os.path.join(dest, 'h264', path[len(source)+1:])
                    if force or (not os.path.exists(dst)) or \
                       not os.stat(dst).st_size or \
                       (os.stat(source)[8] > os.stat(dst)[8]):

                        log.debug("Converting %r to %r"%(path, dst))
                        cmd = [
                            "ffmpeg", 
                            "-y",
                            "-i", path, 
                            "-pass", "1", 
                            "-vcodec", "libx264", 
                            "-vpre", "fastfirstpass", 
                            "-b", "512k", 
                            "-bt", "512k", 
                            "-threads", "0",
                            "-f",  "mp4", 
                            "-an", "/dev/null",
                        ]
                        process = subprocess.Popen(
                            cmd,
                            shell=False, 
                            stdout=subprocess.PIPE, 
                            stderr=subprocess.PIPE,
                        )
                        retcode = process.wait()
                        out, err = process.communicate()
                        if retcode != 0:
                            log.warning(
                                "First pass h264 failed for video %r",
                                path
                            )
                            log.warning('cmd: %s', ' '.join(cmd))
                            log.warning('out: %s', out)
                            log.warning('err: %s', err)
                        else:
                            cmd1 = cmd
                            cmd = [
                                "ffmpeg", 
                                "-y",
                                "-i", path, 
                                "-pass", "2", 
                                "-acodec", "libfaac", 
                                "-ab", "128k", 
                                "-ar", "44100",
                                "-ac", "2", 
                                "-vcodec", "libx264", 
                                "-vpre", "hq", 
                                "-b", "512k", 
                                "-bt", "512k", 
                                "-threads", "0", 
                                "-f", "mp4",
                                dst,
                            ]
                            process = subprocess.Popen(
                                cmd,
                                shell=False, 
                                stdout=subprocess.PIPE, 
                                stderr=subprocess.PIPE,
                            )
                            retcode = process.wait()
                            out, err = process.communicate()
                            if retcode != 0:
                                log.warning(
                                    "Second pass h264 failed for video %r", 
                                    path,
                                )
                                log.warning('1st pass cmd: %s', ' '.join(cmd1))
                                log.warning('2nd pass cmd: %s', ' '.join(cmd))
                                log.warning('out: %s', out)
                                log.warning('err: %s', err)

            #if else:
            #    log.debug("Ignoring %r, unrecognised file type"%path[len(source)+1:])
    sys.exit(1)

def handle_command_metadata(
    option_sets, 
    command_options, 
    args
):
    """\
    usage: ``%(program)s [PROGRAM_OPTIONS] metadata SOURCE DEST [META]``

    Generate a gallery (``-F gallery``) or photo metadata file (``-F photo``)
    from a CSV file.

    If generating a gallery the file can conatin multiple columns but must
    contain the following:

    ``Path``    
      The name to use for the gallery

    ``Title``
      The title of the gallery

    ``Description``  
      A description of the gallery

    ``Index``
      The relative path from the root to a thumbnail to represent the gallery

    If generating photo metadata the file can conatin multiple columns but must
    contain a ``Filename`` column with the path to the photo. Optionally it can
    contain a ``Category`` column specifying the name of the gallery it is to
    appear in. All other columns will just be added with their column headings a
    field names.

    In either case the first line in the CSV file will be treated as the column
    headings.

    Arguments:

      :``SOURCE``: The path to the CSV file
      :``DEST``:   The path to the gallery or photo metadata folder to contain the
                   output from this command.
      :``META``:   The path to the ``meta`` directory (only used with -F gallery)

    Options:
      -F, --format=FORMAT    The type of CSV file we are using, ``photo`` or ``gallery``

      All ``PROGRAM_OPTIONS`` (see \`%(program)s --help')

    Note, only photos can be generated from the CSV file, not videos.
    """
    if not len(args):
        raise getopt.GetoptError('No SOURCE specified')
    elif len(args)<2:
        raise getopt.GetoptError('No DEST specified')
    elif len(args)>3:
        raise getopt.GetoptError('Got unexpected argument %r'%args[3])
    internal_vars = set_error_on(
        command_options, 
        allowed=[
            'format',
            'origin',
        ],
    )
    if not os.path.exists(args[0]):
        raise getopt.GetoptError('No such directory %r'%args[0])
    if not os.path.exists(args[1]):
        raise getopt.GetoptError('No such directory %r'%args[1])
    if len(args) == 3 and not os.path.exists(args[2]):
        raise getopt.GetoptError('No such directory %r'%args[2])
    if not internal_vars.has_key('format'):
        raise getopt.GetoptError('No FORMAT specified')
    elif not internal_vars['format'] in ['photo', 'gallery']:
        raise getopt.GetoptError(
            'Unrecognized FORMAT %r'%internal_vars['format']
        )
    format = internal_vars['format']
    source = os.path.normpath(os.path.abspath(args[0]))
    dest = os.path.normpath(os.path.abspath(args[1]))
    log.info('Starting...')
    import csv
    reader = csv.reader(open(source), delimiter=',', quotechar='"')
    result = []
    headers = None
    first = True
    for row in reader:
        if first:
            headers = row
            first = False
            if format == 'gallery':
                for header in ['Path', 'Title', 'Description', 'Index']:
                    if not header in headers:
                        raise getopt.GetoptError(
                            'No %s column in CSV file'%header
                        )
            elif format == 'photo':
                for header in ['Filename']:
                    if not header in headers:
                        raise getopt.GetoptError(
                            'No %s column in CSV file'%header
                        )
        else:
            new = []
            for i, value in enumerate(row):
                if headers[i] and value:
                    new.append((headers[i].decode('utf-8'), value.decode('utf-8')))
            result.append(new)

    if internal_vars['format'] == 'photo':
        if not len(args) == 2:
            raise getopt.GetoptError(
                'Got an unexpected argument %r'%args[2]
            )
        for photo in result:
            path = None
            for name, value in photo:
                if name == 'Filename':
                    path = value
                    break
            if not path:
                log.debug('Skipping file, no path specified')
            elif not os.path.exists(
                os.path.dirname(os.path.join(dest, path))
            ):
                log.debug(
                    'Skipping %r, parent directory does not exist.',
                    os.path.join(dest, path)
                )
            else:
                save_record(os.path.join(dest, path), photo)
    elif internal_vars['format'] == 'gallery':
        if not len(args) == 3:
            raise getopt.GetoptError(
                'Expected 3 arguments, including the origin directory'
            )
        origin = os.path.normpath(os.path.abspath(args[2]))
        photo_dir = origin
        records = get_all_records(photo_dir)
        for gallery in result:
            path = None
            for name, value in gallery:
                if name == 'Path':
                    path = value
                    break
            if not path:
                log.debug('Skipping file, no path specified')
            elif not os.path.exists(
                os.path.dirname(os.path.join(dest, path))
            ):
                log.debug(
                    'Skipping %r, parent directory does not exist.',
                    os.path.join(dest, path)
                )
            else:
                photo_filenames = []
                for photo_path, photo in records:
                    photo = dict(photo)
                    if photo.get('Category') in [dict(gallery)['Original Path']]:
                        photo_filenames.append(photo_path)
                if not photo_filenames:
                    log.info('Gallery %r contains no photos', path)
                else:
                    gallery.append((u'photos', '| '.join(photo_filenames).decode('utf-8')))
                    direct = os.path.join(dest, dict(gallery)['Year'])
                    if not os.path.exists(direct):
                        os.mkdir(direct)
                    if not os.path.exists(os.path.join(direct, path)):
                        os.mkdir(os.path.join(direct, path))
                    save_record(os.path.join(direct, path, 'index.gallery'), gallery)

#
# API
#

def make_dirs(source, dest):
    bases = ['still', 'h264', '1024', '150', 'exif', 'meta']
    # Make the base directories
    for name in bases:
        if not os.path.exists(os.path.join(dest, name)):
            os.mkdir(os.path.join(dest, name))
    # Find the base directory structure
    to_make = []
    for dirpath, dirnames, filenames in os.walk(source):
        for dirname in dirnames:
            path = os.path.join(dirpath[len(source)+1:], dirname)
            if not path in to_make:
                to_make.append(path)
    for name in bases:
        for path in to_make:
            if not os.path.exists(os.path.join(dest, name, path)):
                os.mkdir(os.path.join(dest, name, path))
            elif not os.path.isdir(os.path.join(dest, name, path)):
                raise getopt.GetoptError(
                    'The path %r already exists but is not a directory'%(
                        os.path.join(dest, name, path)
                    )
                )

orientation_types = {
    1: [],
    2: [],
    3: ['-rotate', '180'],
    4: [],
    5: [],
    6: ['-rotate', '90'],
    7: [],
    8: ['-rotate', '270'],
}

def write(output, photos):
    if not photos:
        log.error("Failed %r", output)
    else:
        record = [
            ('Path', os.path.split(output)[1]),
            ('Title', os.path.split(output)[1]),
            ('Description', 'Auto-generated gallery'),
            ('Index', photos[0]),
            ('photos', '| '.join(photos))
        ]
        output = output.replace(',', '')
        if os.path.exists(output):
            output = output + str(1)
        os.mkdir(output)
        save_record(os.path.join(output, 'index.gallery'), record)

def sort(photos):
    numbered = []
    for path in photos:
        filename = os.path.split(path)[-1]
        number = ''
        for char in filename:
            if char in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
                number += char
        numbered.append((number, path))
    numbered.sort()
    return [x[1] for x in numbered]

def run(dest, meta):
    source = os.path.split(meta)[1]
    source_1024 = os.path.join(source, '1024')
    source_h264 = os.path.join(source, 'h264')
    photos = []
    cur_dirpath = None
    output = None
    for dirpath, dirnames, filenames in os.walk(meta):
        for filename in filenames:
            if filename.startswith('.'):
                log.debug('Ignoring hidden file %r', filename)
                continue
            if filename.split('.')[-1].lower() not in ['cr2', 'png', 'jpg', 'jpeg', 'mpeg','wmv','3gp','mov','mp4','mpg','avi']:
                log.error('Unrecognised file type: %r', filename)
                continue
            if dirpath != cur_dirpath:
                if output is not None:
                    write(output, sort(photos))
                cur_dirpath = dirpath
                output = os.path.join(dest, os.path.split(dirpath)[1].replace(' ','_').lower())
                photos = []
            if filename.split('.')[-1].lower() in ['cr2', 'png', 'jpg', 'jpeg']:
                picpath = dirpath.replace(meta, source_1024)
                if not os.path.isdir(os.path.join(dirpath, filename)):
                    path = relpath(os.path.join(picpath, filename), source_1024)
                    photos.append(path)
            else:
                vidpath = dirpath.replace(meta, source_h264)
                if not os.path.isdir(os.path.join(vidpath, filename)):
                    path = relpath(os.path.join(vidpath, filename), source_h264)
                    photos.append(path)
    # Last one
    if photos:
        write(output, sort(photos))

#
# Option Sets
#

option_sets = {

    'video_overlay_file': [
        dict(
            type = 'command',
            long = ['--video-overlay-file'],
            short = ['-y'],
            metavar = 'OVERLAY_FILE',
        ),
    ],
    'gallery_thumb': [
        dict(
            type = 'command',
            long = ['--gallery-thumb'],
            short = [],
        ),
    ],
    'gallery_reduced': [
        dict(
            type = 'command',
            long = ['--gallery-reduced'],
            short = [],
        ),
    ],
    'gallery_exif': [
        dict(
            type = 'command',
            long = ['--gallery-exif'],
            short = [],
        ),
    ],
    'gallery_h264': [
        dict(
            type = 'command',
            long = ['--gallery-h264'],
            short = [],
        ),
    ],
    'gallery_meta': [
        dict(
            type = 'command',
            long = ['--gallery-meta'],
            short = [],
        ),
    ],
    'gallery_still': [
        dict(
            type = 'command',
            long = ['--gallery-still'],
            short = [],
        ),
    ],
    'config': [
        dict(
            type = 'command',
            long = ['--config'],
            short = ['-c'],
            metavar = 'CONFIG',
        ),
    ],
    'help': [
        dict(
            type = 'shared',
            long = ['--help'],
            short = [],
        ),
    ],
    'version': [
        dict(
            type = 'program',
            long = ['--version'],
            short = [],
        ),
    ],
    'verbose': [
        dict(
            type = 'program',
            long = ['--verbose'],
            short = ['-v'],
        ),
        dict(
            type = 'program',
            long = ['--quiet'],
            short = ['-q'],
        ),
    ]
}

#
# Aliases
#

aliases = {
    'convert'    : ('gt',),
    'csv' : ('gm',),
    'autogen'  : ('gc',),
}

#
# Command factories
#

command_handler_factories = {
    'convert': makeHandler(handle_command_thumb),
    'csv':     makeHandler(handle_command_metadata),
    'autogen': makeHandler(handle_command_gallery),
}

program_help = """usage: %(program)s [PROGRAM_OPTIONS] COMMAND [OPTIONS] ARGS

Commands (aliases):

   :convert:  convert pictures and videos to web format
   :csv:      extract metadata from CSV files
   :autogen:  generate galleries automatically from folders of converted
              pics and vids

Try \`%(program)s COMMAND --help' for help on a specific command.
"""

if __name__ == '__main__':
    program_options, command_options, command, args = parse_command_line(
        option_sets,
        aliases,
    )
    try:
        program_name = os.path.split(sys.argv[0])[1]
        handle_program(
            command_handler_factories=command_handler_factories,
            option_sets=option_sets,
            aliases=aliases,
            program_options=program_options,
            command_options=command_options,
            command=command,
            args=args,
            program_name=program_name,
            help=help_strings,
        )
    except getopt.GetoptError, err:
        # print help information and exit:
        print str(err)
        if command:
            print "Try `%(program)s %(command)s --help' for more information." % {
                'program': os.path.split(sys.argv[0])[1],
                'command': command,
            }
        else:
            print "Try `%(program)s --help' for more information." % {
                'program': os.path.split(sys.argv[0])[1],
            }
        sys.exit(2)
