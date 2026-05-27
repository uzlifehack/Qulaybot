convert="""usage: %(program)s [PROGRAM_OPTIONS] thumb SOURCE DEST

Recursively convert all the pictures and videos in SOURCE into a directory
structure in DEST

Arguments:

   SOURCE:  The source directory for the images and videos
   DEST:    An empty directory which will be populated with a converted
            data structure

Options:

         -t, --thumbnail-size=THUMBNAIL_SIZE
                         The width in pixels of the thumbnails
         -y, --video-overlay-file=OVERLAY_FILE
                         A transparent PNG file the same size as the
                         thumbnails to overlay on video thumbnails to
                         distinguish them from picture thumbnails
         --gallery-exif  Generate EXIF data files
         --gallery-stills
                         Generate video stills
         --gallery-reduced
                         Generate reduced size photos (1024x1024 max)
         --gallery-thumb
                         Generate thumbnails from video stills and
                         reduced sized photos (150x150) and apply the
                         video overlay to the video thubnails
         --gallery-h264  Generate copressed and resized h264 video for
                         use in flash players

        All PROGRAM_OPTIONS (see `%(program)s --help')
"""

csv="""usage: %(program)s [PROGRAM_OPTIONS] metadata SOURCE DEST [META]

Generate a gallery (-F gallery) or photo metadata file (-F photo) from a
CSV file.

If generating a gallery the file can conatin multiple columns but must
contain the following:

Path
        The name to use for the gallery

Title
        The title of the gallery

Description
        A description of the gallery

Index
        The relative path from the root to a thumbnail to represent the
        gallery

If generating photo metadata the file can conatin multiple columns but
must contain a Filename column with the path to the photo. Optionally it
can contain a Category column specifying the name of the gallery it is to
appear in. All other columns will just be added with their column headings
a field names.

In either case the first line in the CSV file will be treated as the
column headings.

Arguments:

   SOURCE:  The path to the CSV file
   DEST:    The path to the gallery or photo metadata folder to contain
            the output from this command.
   META:    The path to the meta directory (only used with -F gallery)

Options:

         -F, --format=FORMAT
              The type of CSV file we are using, photo or gallery

        All PROGRAM_OPTIONS (see `%(program)s --help')

Note, only photos can be generated from the CSV file, not videos.
"""

autogen="""usage: %(program)s [PROGRAM_OPTIONS] gallery META DEST

Automatically build galleries based on the file strucutre of the meta
directory specified as META and put them in DEST. It needs the h264 and
1024 directoires too to create the create links.

The order of files is a gallery is determined by stripping all characters
which aren't numbers from the filename and then numbering the files in
order

Arguments:

   META:  The path to the photo and video metadata directory
   DEST:  An empty directory within which the galleries will be placed

  All PROGRAM_OPTIONS (see `%(program)s --help')
"""

__program__="""usage: %(program)s [PROGRAM_OPTIONS] COMMAND [OPTIONS] ARGS

Commands (aliases):

   convert:  convert pictures and videos to web format
   csv:      extract metadata from CSV files
   autogen:  generate galleries automatically from folders of converted
             pics and vids

Try `%(program)s COMMAND --help' for help on a specific command.
"""

