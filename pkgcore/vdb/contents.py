# Copyright: 2005-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.fs.contents import contentsSet
from pkgcore.fs import fs
from pkgcore.interfaces import data_source

from snakeoil.fileutils import AtomicWriteFile
from snakeoil.compatibility import any
from snakeoil.demandload import demandload
demandload(globals(),
    'os',
    'stat',
    'errno',
    'pkgcore.chksum:get_handler',
    'snakeoil.osutils:readlines',
)

class LookupFsDev(fs.fsDev):

    def __init__(self, path, **kwds):
        if any(x not in kwds for x in ("major", "minor", "mode")):
            try:
                st = os.lstat(path)
            except OSError, oe:
                if oe.errno != errno.ENOENT:
                    raise
                st = None
            if st is None or any(f(st.st_mode) for f in
                (stat.S_ISREG, stat.S_ISDIR, stat.S_ISFIFO)):
                kwds["strict"] = True
            else:
                major, minor = fs.get_major_minor(st)
                kwds["major"] = major
                kwds["minor"] = minor
                kwds["mode"] = st.st_mode
        fs.fsDev.__init__(self, path, **kwds)


class ContentsFile(contentsSet):
    """class wrapping a contents file"""

    def __init__(self, source, mutable=False, create=False):

        if not isinstance(source, (data_source.base, basestring)):
            raise TypeError("source must be either data_source, or a filepath")
        contentsSet.__init__(self, mutable=True)
        self._source = source

        if not create:
            self._read()

        self.mutable = mutable

    def clone(self, empty=False):
        # create is used to block it from reading.
        cset = self.__class__(self._source, mutable=True, create=True)
        if not empty:
            cset.update(self)
        return cset

    def add(self, obj):
        if isinstance(obj, fs.fsFile):
            # strict checks
            if obj.chksums is None or "md5" not in obj.chksums:
                raise TypeError("fsFile objects need to be strict")
        elif not isinstance(obj, (fs.fsDir, fs.fsSymlink, fs.fsFifo, fs.fsDev)):
            raise TypeError(
                "obj must be of fsObj, fsDir, fsLink, fsFifo, fsDev class "
                "or derivative")

        contentsSet.add(self, obj)

    def _get_fd(self, write=False):
        if isinstance(self._source, basestring):
            if write:
                return AtomicWriteFile(self._source)
            return readlines(self._source, True)
        fobj = self._source.get_fileobj()
        if write:
            fobj.seek(0, 0)
            fobj.truncate(0)
        return fobj

    def flush(self):
        return self._write()

    def _parse_old(self, line):
        """parse old contents, non tab based format"""
        # specifically force splitting on spaces.
        s = line.split()
        if not s:
            # stupid; just whitespace/newline.  ignore it.
            return None
        if s[0] in ("dir", "dev", "fif"):
            return s[0], ' '.join(s[1:])
        elif s[0] == "obj":
            return "obj", ' '.join(s[1:-2]), s[-2], s[-1]
        elif s[0] == "sym":
            try:
                p = s.index("->")
                return "sym", ' '.join(s[1:p]), ' '.join(s[p+1:-1]), long(s[-1])

            except ValueError:
                # XXX throw a corruption error
                raise
        else:
            return s[0], ' '.join(s[1:])

    def _read(self):
        self.clear()
        for line in self._get_fd():
            line = self._parse_old(line)
            if line is None:
                continue
#            if "\t" not in line:
#                line = self._parse_old(line)
#            else:
#                line = line.split("\t")

            if line[0] == "dir":
                obj = fs.fsDir(line[1], strict=False)
            elif line[0] == "fif":
                obj = fs.fsDir(line[1], strict=False)
            elif line[0] == "dev":
                obj = LookupFsDev(line[1], strict=False)
            elif line[0] == "obj":
                #file: path, md5, time
                obj = fs.fsFile(
                    line[1], chksums={"md5":long(line[2], 16)},
                        mtime=long(line[3]),
                    strict=False)
            elif line[0] == "sym":
                #path, target, ' -> ', mtime
                obj = fs.fsLink(
                    line[1], line[2], mtime=line[3], strict=False)
            else:
                if len(line) > 2:
                    line = line[0], ' '.join(line[1:])
                raise Exception(
                    "unknown entry type %s: %s" % (line[0], line[1]))
            self.add(obj)

    def _write(self):
        md5_handler = get_handler('md5')
        outfile = None
        try:
            outfile = self._get_fd(True)

            for obj in sorted(self):

                if isinstance(obj, fs.fsFile):
                    s = " ".join(("obj", obj.location,
                        md5_handler.long2str(obj.chksums["md5"]),
                        str(long(obj.mtime))))

                elif isinstance(obj, fs.fsLink):
                    s = " ".join(("sym", obj.location, "->",
                                   obj.target, str(long(obj.mtime))))

                elif isinstance(obj, fs.fsDir):
                    s = "dir " + obj.location

                elif isinstance(obj, fs.fsDev):
                    s = "dev " + obj.location

                elif isinstance(obj, fs.fsFifo):
                    s = "fif " + obj.location

                else:
                    raise Exception(
                        "unknown type %s: %s" % (type(obj), obj))
                outfile.write(s + "\n")
            outfile.close()

        finally:
            # if atomic, it forces the update to be wiped.
            del outfile
