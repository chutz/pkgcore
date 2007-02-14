# Copyright: 2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.merge import triggers, const
from pkgcore.fs import fs, contents
from pkgcore.fs.livefs import gen_obj, scan
from pkgcore.util.currying import partial
from pkgcore.util.osutils import pjoin, ensure_dirs, normpath
from pkgcore import spawn
from pkgcore.test import TestCase, SkipTest, mixins
import os, shutil, time
from math import floor, ceil


class fake_trigger(triggers.base):

    def __init__(self, **kwargs):
        self._called = []
        if isinstance(kwargs.get('_hooks', False), basestring):
            kwargs['_hooks'] = (kwargs['_hooks'],)
        for k, v in kwargs.iteritems():
            if callable(v):
                v = patrial(v, self)
            setattr(self, k, v)

    def trigger(self, *args):
        self._called.append(args)


class fake_engine(object):

    def __init__(self, **kwargs):
        self._triggers = []
        for k, v in kwargs.iteritems():
            if callable(v):
                v = partial(v, self)
            setattr(self, k, v)

    def add_trigger(self, hook_point, trigger, required_csets):
        if hook_point in getattr(self, "blocked_hooks", []):
            raise KeyError(hook_point)
        self._triggers.append((hook_point, trigger, required_csets))


class TestBase(TestCase):

    kls = fake_trigger
    
    def mk_trigger(self, kls=None, **kwargs):
        if kls is None:
            kls = self.kls
        return kls(**kwargs)

    def test_default_attrs(self):
        for x in ("required_csets", "_label", "_hooks", "_engine_types"):
            self.assertEqual(None, getattr(self.kls, x),
                msg="%s must exist and be None" % x)
        self.assertEqual(50, self.kls._priority)

    def test_label(self):
        self.assertEqual(self.mk_trigger().label, str(self.kls.__name__))
        self.assertEqual(fake_trigger().label, str(fake_trigger.__name__))
        self.assertEqual(fake_trigger(_label='foon').label, 'foon')

    def test_priority(self):
        self.assertEqual(fake_trigger(_priority=50).priority, 50)
        self.assertEqual(fake_trigger(_priority=10000).priority, 10000)
        self.assertEqual(fake_trigger(_priority=0).priority, 0)

    def test_localize(self):
        o = self.mk_trigger()
        self.assertEqual(o, o.localize(None))

    def test_get_required_csets(self):
        self.assertEqual(fake_trigger(required_csets=None).get_required_csets(
            None), None)
        self.assertEqual(fake_trigger(required_csets=None).get_required_csets(
            1), None)
        self.assertEqual(fake_trigger(required_csets=None).get_required_csets(
            ""), None)
        o = fake_trigger(required_csets={"foo":["dar"], "bar":1})
        self.assertEqual(o.get_required_csets("foo"), ["dar"])
        self.assertEqual(o.get_required_csets("bar"), 1)
        self.assertEqual(fake_trigger(required_csets=("dar", "foo"))
            .get_required_csets("bar"), ("dar", "foo"))
        self.assertEqual(fake_trigger(required_csets=())
            .get_required_csets(""), ())

    def test_register(self):
        engine = fake_engine(mode=1)
        self.assertRaises(TypeError, self.mk_trigger(mode=1).register, engine)
        self.assertRaises(TypeError, self.mk_trigger(mode=1, _hooks=2).register,
            engine)
        self.assertFalse(engine._triggers)
        
        # shouldn't puke.
        o = self.mk_trigger(mode=1, _hooks=("2"))
        o.register(engine)
        self.assertEqual(engine._triggers, [('2', o, None)])
        engine._triggers = []

        # verify it's treating "all csets" differently from "no csets"
        o = self.mk_trigger(mode=1, _hooks=("2"), required_csets=())
        o.register(engine)
        self.assertEqual(engine._triggers, [('2', o, ())])
        
        # should handle keyerror thrown from the engine for missing hooks.
        engine = fake_engine(mode=1, blocked_hooks=("foon", "dar"))
        self.mk_trigger(mode=1, _hooks="foon").register(engine)
        self.mk_trigger(mode=1, _hooks=("foon", "dar")).register(engine)
        self.assertFalse(engine._triggers)
        
        o = self.mk_trigger(mode=1, _hooks=("foon", "bar"), required_csets=(3,))
        o.register(engine)
        self.assertEqual(engine._triggers, [('bar', o, (3,))])
        engine._triggers = []
        o = self.mk_trigger(mode=1, _hooks="bar", required_csets=None)
        o.register(engine)
        self.assertEqual(engine._triggers, [('bar', o, None)])

    def test_call(self):
        # test "I want all csets"
        def get_csets(required_csets, csets, fallback=None):
            o = self.mk_trigger(required_csets={1:required_csets, 2:fallback},
                mode=(1,))
            engine = fake_engine(csets=csets, mode=1)
            o(engine, csets)
            self.assertEqual([x[0] for x in o._called],
                [engine]*len(o._called))
            return [list(x[1:]) for x in o._called]

        d = object()
        self.assertEqual(get_csets(None, d, [1]), [[d]], 
            msg="raw csets mapping should be passed through without conversion"
                " for required_csets=None")

        self.assertEqual(get_csets([1,2], {1:1,2:2}), [[1, 2]],
            msg="basic mapping through failed")
        self.assertEqual(get_csets([], {}), [[]],
            msg="for no required csets, must have no args passed")


class test_module(TestCase):

    def test_constants(self):
        self.assertEqual(sorted([const.REPLACE_MODE, const.UNINSTALL_MODE]),
            sorted(triggers.UNINSTALLING_MODES))
        self.assertEqual(sorted([const.REPLACE_MODE, const.INSTALL_MODE]),
            sorted(triggers.INSTALLING_MODES))


class Test_mtime_watcher(mixins.TempDirMixin, TestCase):

    kls = triggers.mtime_watcher

    def test_identification(self):
        o = [gen_obj(self.dir)]
        t = self.kls()
        t.set_state([self.dir])
        self.assertEqual(list(t.saved_mtimes),
            o)
        open(pjoin(self.dir, 'file'), 'w')
        t.set_state([self.dir, pjoin(self.dir, 'file')])
        self.assertEqual(list(t.saved_mtimes), o)
        loc = pjoin(self.dir, 'dir')
        os.mkdir(loc)
        o.append(gen_obj(pjoin(self.dir, 'dir')))
        o.sort()
        t.set_state([x.location for x in o])
        self.assertEqual(sorted(t.saved_mtimes), o)
        
        # test syms.
        src = pjoin(self.dir, 'dir2')
        os.mkdir(src)
        loc = pjoin(self.dir, 'foo')
        os.symlink(src, loc)
        locs = [x.location for x in o]

        # insert a crap location to ensure it handles it.
        locs.append(pjoin(self.dir, "asdfasdfasdfasfdasdfasdfasdfasdf"))

        locs.append(src)
        i = gen_obj(src, stat=os.stat(src))
        o.append(i)
        o.sort()
        t.set_state(locs)
        self.assertEqual(sorted(t.saved_mtimes), o)
        locs[-1] = loc
        o.remove(i)
        i = i.change_attributes(location=loc)
        o.append(i)
        o.sort()
        t.set_state(locs)
        self.assertEqual(sorted(t.saved_mtimes), o)

        o.remove(i)
        os.rmdir(src)

        # check stat_func usage; if lstat, the sym won't be derefed,
        # thus ignored.
        t.set_state(locs, stat_func=os.lstat)
        self.assertEqual(sorted(t.saved_mtimes), o)
        open(pjoin(self.dir, 'bar'), 'w')
        self.assertTrue(t.check_state())

        # test dead sym filtering for stat.
        t.set_state(locs)
        self.assertEqual(sorted(t.saved_mtimes), o)
        self.assertFalse(t.check_state())
    
    def test_float_mtime(self):
        cur = os.stat_float_times()
        try:
            t = self.kls()
            t.set_state([self.dir])
            l = list(t.saved_mtimes)
            self.assertEqual(len(l), 1)
            l = l[0]
            self.assertTrue(isinstance(l.mtime, float),
                msg="mtime *must* be a float got %r" % l.mtime)
        finally:
            os.stat_float_times(cur)

    def test_race_protection(self):
        # note this isn't perfect- being a race, triggering it on 
        # demand is tricky.
        # hence the 10x loop; can trigger it pretty much each loop
        # for my 1ghz, so... it's a start.
        # the race specifically will only rear it's head on extremely
        # fast io (crazy hardware, or async mount), fs's lacking subsecond,
        # and just severely crappy chance.
        # faster the io actions, easier it is to trigger.
        cur = os.stat_float_times()
        try:
            t = self.kls()
            os.stat_float_times(True)
            for x in xrange(10):
                now = ceil(time.time()) + 1
                os.utime(self.dir, (now + 100, now + 100))
                t.set_state([self.dir])
                while now > ceil(time.time()):
                    t.set_state([self.dir])
                now, st_mtime = time.time(), os.stat(self.dir).st_mtime
                now, st_mtime = ceil(now), floor(st_mtime)
                self.assertTrue(now > st_mtime,
                    msg="%r must be > %r" % (now, st_mtime))
        finally:
            os.stat_float_times(cur)


def castrate_trigger(base_kls, **kwargs):
    class castrated_trigger(base_kls):

        enable_regen = False
        def __init__(self, *args2, **kwargs2):
            self._passed_in_args = []
            base_kls.__init__(self, *args2, **kwargs2)
    
        def regen(self, *args):
            self._passed_in_args.append(list(args))
            if self.enable_regen:
                return base_kls.regen(self, *args)
            return []

        locals().update(kwargs)

    return castrated_trigger


class trigger_mixin(mixins.TempDirMixin):
    
    def setUp(self):
        mixins.TempDirMixin.setUp(self)
        self.reset_objects()

    def reset_objects(self, mode=const.INSTALL_MODE):
        self.engine = fake_engine(offset=self.dir, mode=mode)
        self.trigger = self.kls()

    def assertPaths(self, expected, tested):
        expected = sorted(expected)
        tested = sorted(tested)
        self.assertEqual(expected, tested,
            msg="expected %r, got %r" % (expected, tested))


class Test_ldconfig(trigger_mixin, TestCase):

    # use the kls indirection for when *bsd version of ldconfig trigger
    # is derived; will be pretty much the same, sans the trigger call.

    kls = castrate_trigger(triggers.ldconfig)

    def test_read_ld_so_conf(self):
        # test the defaults first.  should create etc and the file.
        self.assertPaths(self.trigger.read_ld_so_conf(self.dir),
            [pjoin(self.dir, x) for x in self.trigger.default_ld_path])
        o = gen_obj(pjoin(self.dir, 'etc'))
        self.assertEqual(o.mode, 0755)
        self.assertTrue(fs.isdir(o))
        self.assertTrue(os.path.exists(pjoin(self.dir, 'etc/ld.so.conf')))
        
        # test normal functioning.
        open(pjoin(self.dir, 'etc/ld.so.conf'), 'w').write("\n".join(
            ["/foon", "dar", "blarnsball", "#comment"]))
        self.assertPaths(self.trigger.read_ld_so_conf(self.dir),
            [pjoin(self.dir, x) for x in ["foon", "dar", "blarnsball"]])

    def assertTrigger(self, touches, ran, dirs=['test-lib', 'test-lib2'],
        hook='merge', mode=const.INSTALL_MODE, mkdirs=True, same_mtime=False):
        
        # wipe whats there.
        for x in scan(self.dir).iterdirs():
            if x.location == self.dir:
                continue
            shutil.rmtree(x.location)
        for x in scan(self.dir).iterdirs(True):
            os.unlink(x.location)

        ensure_dirs(pjoin(self.dir, "etc"))
        open(pjoin(self.dir, "etc/ld.so.conf"), "w").write(
            "\n".join('/' + x for x in dirs))
        # force directory mtime to 1s less.
        past = time.time() - 10.0
        if mkdirs:
            for x in dirs:
                ensure_dirs(pjoin(self.dir, x))
                os.utime(pjoin(self.dir, x), (past, past))

        self.reset_objects()
        self.engine.phase = 'pre_%s' % hook
        self.engine.mode = mode
        self.trigger(self.engine, {})
        self.assertFalse(self.trigger._passed_in_args)
        resets = set()
        for x in touches:
            fp = pjoin(self.dir, x.lstrip('/'))
            open(pjoin(fp), "w")
            if same_mtime:
                os.utime(fp, (past, past))
                resets.add(os.path.dirname(fp))

        for x in resets:
            os.utime(x, (past, past))

        self.engine.phase = 'post_%s' % hook
        self.trigger(self.engine, {})

        if ran:
            self.assertEqual(self.trigger._passed_in_args, [[self.dir]])
        else:
            self.assertEqual(self.trigger._passed_in_args, [])

    def test_trigger(self):
        # ensure it doesn't explode for missing dirs.
        self.assertTrigger([], False, mkdirs=False)
        self.assertTrigger([], False)
        self.assertTrigger(['test-lib/foon'], True)
        self.assertTrigger(['test-lib/foon'], False, same_mtime=True)


class TestInfoRegen(trigger_mixin, TestCase):

    raw_kls = triggers.InfoRegen
    @property
    def kls(self):
        return castrate_trigger(self.raw_kls, locations=['/'])

    info_data = \
"""INFO-DIR-SECTION Network Applications
START-INFO-DIR-ENTRY
* Wget: (wget).         The non-interactive network downloader.
END-INFO-DIR-ENTRY
"""

    def reset_objects(self, **kwargs):
        trigger_mixin.reset_objects(self, **kwargs)
        self.trigger.location = [self.dir]

    def test_binary_path(self):
        existing = os.environ.get("PATH", self)
        try:
            try:
                path = spawn.find_binary('install-info')
            except spawn.CommandNotFound:
                path = None
            self.assertEqual(path, self.trigger.get_binary_path())
            if path is not self:
                os.environ["PATH"] = ""
                self.assertEqual(None, self.trigger.get_binary_path())
        finally:
            if existing is self:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = existing

    def test_regen(self):
        o = self.raw_kls()
        path = o.get_binary_path()
        if path is None:
            raise SkipTest("can't verify regen behaviour due to install-info "
                "not being available")
        open(pjoin(self.dir, "foo.info"), 'w').write(self.info_data)
        # no issues.
        self.assertEqual(list(o.regen(path, self.dir)), [])
        self.assertTrue(os.path.exists(pjoin(self.dir, 'dir')),
            msg="info dir file wasn't created")
        
        # drop the last line, verify it returns that file.
        open(pjoin(self.dir, "foo2.info"), 'w').write(
            '\n'.join(self.info_data.splitlines()[:-1]))
        os.unlink(pjoin(self.dir, 'dir'))
        self.assertEqual(list(o.regen(path, self.dir)),
            [pjoin(self.dir, 'foo2.info')])
        self.assertTrue(os.path.exists(pjoin(self.dir, 'dir')),
            msg="info dir file wasn't created")

    def run_trigger(self, phase, expected_regen=[]):
        l = []
        class foo:
            warn = staticmethod(l.append)
        self.engine.observer = foo()
        self.trigger._passed_in_args = []
        self.engine.phase = phase
        self.trigger(self.engine, {})
        self.assertEqual(map(normpath, (x[1] for x in self.trigger._passed_in_args)), 
            map(normpath, expected_regen))
        return l
        
    def test_trigger(self):
        cur = os.environ.get("PATH", self)
        try:
            os.environ.pop("PATH", None)
            # shouldn't run if the binary is missing
            # although it should warn, and this code will explode when it does.
            self.assertEqual(None, self.trigger(self.engine, {}))
        finally:
            if cur is not self:
                os.environ["PATH"] = cur

        # verify it runs when dir is missing.
        # doesn't create the file since no info files.
        self.reset_objects()
        self.assertFalse(self.run_trigger('pre_merge', []))
        self.assertFalse(self.run_trigger('post_merge', [self.dir]))

        # and an info, and verify it generated.
        open(pjoin(self.dir, 'foo.info'), 'w').write(self.info_data)
        self.reset_objects()
        self.trigger.enable_regen = True
        self.assertFalse(self.run_trigger('pre_merge', []))
        self.assertFalse(self.run_trigger('post_merge', [self.dir]))

        # verify it doesn't; mtime is fine
        self.reset_objects()
        self.trigger.enable_regen = True
        self.assertFalse(self.run_trigger('pre_merge', []))
        self.assertFalse(self.run_trigger('post_merge', []))

        # verify it handles quoting properly, and that it ignores 
        # complaints about duplicates.
        self.reset_objects()
        self.trigger.enable_regen = True
        self.assertFalse(self.run_trigger('pre_merge', []))
        open(pjoin(self.dir, "blaidd drwg.info"), "w").write(self.info_data)
        self.assertFalse(self.run_trigger('post_merge', [self.dir]))
        
        # verify it passes back failures.
        self.reset_objects()
        self.trigger.enable_regen = True
        self.assertFalse(self.run_trigger('pre_merge', []))
        open(pjoin(self.dir, "tiza grande.info"), "w").write(
            '\n'.join(self.info_data.splitlines()[:-1]))
        l = self.run_trigger('post_merge', [self.dir])
        self.assertEqual(len(l), 1)
        self.assertIn('tiza grande.info', l[0])

        # verify it holds off on info regen till after unmerge for replaces.
        self.reset_objects(mode=const.REPLACE_MODE)
        self.assertFalse(self.run_trigger('pre_merge', []))
        self.assertFalse(self.run_trigger('post_merge', []))
        self.assertFalse(self.run_trigger('pre_unmerge', []))
        os.unlink(pjoin(self.dir, "tiza grande.info"))
        self.assertFalse(self.run_trigger('post_unmerge', [self.dir]))
        
