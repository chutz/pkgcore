# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from twisted.trial import unittest
from pkgcore.pkgsets.filelist import FileList
from pkgcore.ebuild.atom import atom
import tempfile, os

class TestFileList(unittest.TestCase):
    def setUp(self):
        self.fn = tempfile.mktemp()

    def tearDown(self):
        try:
            os.unlink(self.fn)
        except IOError:
            pass

    def gen_world(self, contents):
        open(self.fn, "w").write(contents)
        return FileList(self.fn)

    def test_contains(self):
        self.assertIn(
            atom("x11-base/xorg-x11"), self.gen_world("x11-base/xorg-x11"))

    def test_len(self):
        self.assertEqual(
            len(self.gen_world("x11-base/xorg-x11\ndev-util/diffball")), 2)

    def test_iter(self):
        self.assertEqual(
            sorted(self.gen_world("dev-util/diffball\ndev-util/bsdiff")),
            sorted(atom(x) for x in ["dev-util/diffball", "dev-util/bsdiff"]))
