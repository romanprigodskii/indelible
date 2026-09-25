"""Core library and setup commands: io, dates, workspace, learning logic, doctor/init/subject/set/schema."""

import json
import os
import shutil
import socket
import tempfile
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from helpers import CLI, SKILL_DIR, make_ws, run
except ImportError:  # run as part of the tests package
    from tests.helpers import CLI, SKILL_DIR, make_ws, run

from lib import DataError, LockBusy
from lib import dates, learning, schema
from lib import io as fio
from lib import ws as wsmod

NOW = "2026-10-12T09:00+01:00"


class Base(unittest.TestCase):
    """Sets INDELIBLE_NOW for in-process code and gives each test a temp folder."""

    def setUp(self):
        self._old_now = os.environ.get("INDELIBLE_NOW")
        os.environ["INDELIBLE_NOW"] = NOW
        self.tmp = Path(tempfile.mkdtemp(prefix="indelible-core-"))

    def tearDown(self):
        if self._old_now is None:
            os.environ.pop("INDELIBLE_NOW", None)
        else:
            os.environ["INDELIBLE_NOW"] = self._old_now
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def bare_ws(self, name="ws"):
        root = self.tmp / name
        root.mkdir(parents=True)
        (root / "indelible.json").write_text('{"v": 1, "subjects": []}\n', encoding="utf-8")
        return root


# ==========================================================================
# io
# ==========================================================================

class IoTests(Base):
    def test_write_json_is_atomic_and_keeps_bak(self):
        p = self.tmp / "data" / "x.json"
        fio.write_json(p, {"a": 1, "t": "x² → é"})
        self.assertEqual(fio.read_json(p), {"a": 1, "t": "x² → é"})
        self.assertFalse(fio.bak_path(p).exists())
        fio.write_json(p, {"a": 2})
        self.assertEqual(fio.read_json(p), {"a": 2})
        self.assertEqual(fio.read_json(fio.bak_path(p)), {"a": 1, "t": "x² → é"})
        leftovers = [f.name for f in p.parent.iterdir() if f.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])
        self.assertIn("x² → é", fio.bak_path(p).read_text(encoding="utf-8"))

    def test_write_jsonl_snapshot_and_missing_files(self):
        p = self.tmp / "rows.jsonl"
        self.assertEqual(fio.read_jsonl(p), [])
        self.assertIsNone(fio.read_json(self.tmp / "none.json"))
        self.assertEqual(fio.read_json(self.tmp / "none.json", default={}), {})
        fio.write_jsonl(p, [{"id": 1}, {"id": 2}])
        self.assertEqual(fio.read_jsonl(p), [{"id": 1}, {"id": 2}])
        self.assertEqual(p.read_text(encoding="utf-8"), '{"id":1}\n{"id":2}\n')

    def test_corrupt_json_raises_data_error(self):
        p = self.tmp / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        with self.assertRaises(DataError):
            fio.read_json(p)

    def test_bom_and_crlf_are_accepted(self):
        p = self.tmp / "bom.json"
        p.write_bytes(b'\xef\xbb\xbf{"a": "\xc3\xa9"}\r\n')
        self.assertEqual(fio.read_json(p), {"a": "é"})
        q = self.tmp / "crlf.jsonl"
        q.write_bytes(b'\xef\xbb\xbf{"n": 1}\r\n{"n": 2}\r\n\r\n')
        self.assertEqual(fio.read_jsonl(q, quarantine=False), [{"n": 1}, {"n": 2}])

    def test_bad_lines_are_quarantined_once(self):
        root = self.bare_ws()
        p = root / "ielts" / "data" / "attempts.jsonl"
        fio.append_jsonl(p, {"v": 1, "n": 1})
        with open(p, "a", encoding="utf-8") as fh:
            fh.write("{broken\n[1, 2]\n")
        fio.append_jsonl(p, {"v": 1, "n": 2})
        rows = fio.read_jsonl(p)
        self.assertEqual([r["n"] for r in rows], [1, 2])
        q = fio.read_quarantine(root)
        self.assertEqual(len(q), 2)
        self.assertEqual(q[0]["file"], "ielts/data/attempts.jsonl")
        self.assertEqual(q[0]["line_no"], 2)
        self.assertEqual(q[0]["text"], "{broken")
        self.assertEqual(q[1]["line_no"], 3)
        fio.read_jsonl(p)  # reading again does not duplicate
        self.assertEqual(fio.quarantine_count(root), 2)
        self.assertTrue((root / ".indelible" / "quarantine.jsonl").exists())

    def test_append_after_torn_line_starts_a_new_line(self):
        root = self.bare_ws()
        p = root / "ledger.jsonl"
        p.write_text('{"v":1,"id":"L-0001"}\n{"v":1,"id":"L-00', encoding="utf-8")
        fio.append_jsonl(p, {"v": 1, "id": "L-0003"})
        rows = fio.read_jsonl(p)
        self.assertEqual([r["id"] for r in rows], ["L-0001", "L-0003"])
        self.assertEqual(fio.quarantine_count(root), 1)

    def test_write_lock_is_exclusive_reentrant_and_clears_stale(self):
        root = self.bare_ws()
        lock_file = root / ".indelible" / "write.lock"
        with fio.write_lock(root):
            self.assertTrue(lock_file.exists())
            info = json.loads(lock_file.read_text(encoding="utf-8"))
            self.assertEqual(info["pid"], os.getpid())
            with fio.write_lock(root):  # re-entry in the same process
                self.assertTrue(lock_file.exists())
            self.assertTrue(lock_file.exists())
        self.assertFalse(lock_file.exists())

        other = {"pid": os.getppid(), "host": socket.gethostname(), "at": "now", "epoch": time.time()}
        lock_file.write_text(json.dumps(other), encoding="utf-8")
        with self.assertRaises(LockBusy):
            fio.WriteLock(root, timeout=0.3).acquire()
        self.assertTrue(lock_file.exists())

        other["epoch"] = time.time() - 11 * 60  # older than 10 minutes: stale
        lock_file.write_text(json.dumps(other), encoding="utf-8")
        with fio.write_lock(root, timeout=0.3):
            info = json.loads(lock_file.read_text(encoding="utf-8"))
            self.assertEqual(info["pid"], os.getpid())
        self.assertFalse(lock_file.exists())


# ==========================================================================
# dates
# ==========================================================================

class DatesTests(Base):
    def test_parse_iso_normalises_provider_forms(self):
        utc7 = datetime(2026, 10, 15, 7, 0, tzinfo=timezone.utc)
        self.assertEqual(dates.parse_iso("2026-10-15T07:00:00.000+0000"), utc7)
        self.assertEqual(dates.parse_iso("2026-10-15T07:00:00Z"), utc7)
        self.assertEqual(dates.parse_iso("2026-10-15T07:00Z"), utc7)
        self.assertEqual(dates.parse_iso("2026-10-15T08:00+01:00"), utc7)
        self.assertEqual(dates.parse_iso("2026-10-15T08:00:00+0100"), utc7)
        self.assertEqual(dates.parse_iso("2026-10-15T09:00+02"), utc7)
        self.assertEqual(dates.parse_iso("20261015T070000Z"), utc7)
        d = dates.parse_iso("2026-10-15T07:00:00.1234567+00:00")
        self.assertEqual(d.microsecond, 123456)
        self.assertEqual(dates.parse_iso("2026-10-15T07:00:00.000+0000").utcoffset(), timedelta(0))

    def test_parse_iso_rejects_garbage(self):
        for bad in ("", "tomorrow", "2026-13-01", "2026-10-15T25:00+01:00", "15/10/2026"):
            with self.assertRaises(ValueError):
                dates.parse_iso(bad)

    def test_naive_times_get_the_local_offset(self):
        self.assertEqual(dates.fmt_iso(dates.parse_iso("2026-10-15T07:00")), "2026-10-15T07:00+01:00")

    def test_now_honours_indelible_now(self):
        self.assertEqual(dates.fmt_iso(dates.now()), NOW)
        self.assertEqual(dates.today(), date(2026, 10, 12))
        os.environ["INDELIBLE_NOW"] = "2026-10-15T07:00:00Z"
        self.assertEqual(dates.fmt_iso(dates.now()), "2026-10-15T07:00+00:00")

    def test_fmt_and_to_date(self):
        self.assertEqual(dates.fmt_iso(dates.parse_iso("2026-10-15T07:00:59+01:00")), "2026-10-15T07:00+01:00")
        self.assertEqual(dates.fmt_iso("2026-10-15T07:00:59+01:00", seconds=True), "2026-10-15T07:00:59+01:00")
        self.assertEqual(dates.fmt_iso(datetime(2026, 10, 15, 7, 0, tzinfo=timezone(timedelta(hours=-5)))),
                         "2026-10-15T07:00-05:00")
        self.assertEqual(dates.to_date("2026-10-15T23:30+01:00"), date(2026, 10, 15))
        self.assertEqual(dates.to_date("2026-10-15"), date(2026, 10, 15))
        self.assertEqual(dates.fmt_date(date(2026, 1, 2)), "2026-01-02")
        self.assertEqual(dates.iso_week("2026-10-12"), "2026-W42")

    def test_weekdays_and_arithmetic(self):
        self.assertEqual(dates.weekday_name(date(2026, 10, 12)), "Mon")
        self.assertEqual(dates.weekday_name("2026-10-18", long=True), "Sunday")
        self.assertEqual(dates.weekday_index("thursday"), 3)
        self.assertEqual(dates.expand_days("Mon-Fri"), ["Mon", "Tue", "Wed", "Thu", "Fri"])
        self.assertEqual(dates.expand_days("Sat,Sun"), ["Sat", "Sun"])
        self.assertEqual(dates.expand_days(["Tue", "Thu"]), ["Tue", "Thu"])
        self.assertEqual(dates.hours_between("2026-10-13T07:00+01:00", "2026-10-15T08:00+01:00"), 49.0)
        self.assertEqual(dates.hours_between("2026-10-15T08:00+01:00", "2026-10-15T07:00Z"), 0.0)
        self.assertEqual(dates.add_days("2026-10-30", 3), date(2026, 11, 2))
        self.assertEqual(dates.fmt_iso(dates.at_time("2026-10-15", "07:30")), "2026-10-15T07:30+01:00")
        self.assertTrue(dates.is_hhmm("23:00"))
        self.assertFalse(dates.is_hhmm("7pm"))


# ==========================================================================
# workspace discovery, subjects and ids
# ==========================================================================

class WorkspaceTests(Base):
    def test_discovery_order(self):
        flag_ws, env_ws, cwd_ws, ptr_ws = (self.bare_ws(n) for n in ("flag", "env", "cwd", "ptr"))
        deep = cwd_ws / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        too_deep = deep / "e"
        too_deep.mkdir()
        pointer = self.tmp / "home" / ".indelible" / "workspace"
        pointer.parent.mkdir(parents=True)
        pointer.write_text(str(ptr_ws) + "\n", encoding="utf-8")
        env = {wsmod.ENV_WORKSPACE: str(env_ws)}

        root, src, _ = wsmod.discover(flag=str(flag_ws), environ=env, cwd=deep, pointer=pointer)
        self.assertEqual((root, src), (flag_ws.resolve(), "flag"))
        root, src, _ = wsmod.discover(flag=None, environ=env, cwd=deep, pointer=pointer)
        self.assertEqual((root, src), (env_ws.resolve(), "env"))
        root, src, _ = wsmod.discover(flag=None, environ={}, cwd=deep, pointer=pointer)
        self.assertEqual((root, src), (cwd_ws.resolve(), "cwd"))
        root, src, _ = wsmod.discover(flag=None, environ={}, cwd=too_deep, pointer=pointer)
        self.assertEqual((root, src), (ptr_ws.resolve(), "pointer"))
        root, src, _ = wsmod.discover(flag=None, environ={}, cwd=self.tmp, pointer=self.tmp / "nothing")
        self.assertEqual((root, src), (None, "none"))
        # an explicit flag that holds no workspace is not passed over
        empty = self.tmp / "empty"
        empty.mkdir()
        root, src, detail = wsmod.discover(flag=str(empty), environ=env, cwd=deep, pointer=pointer)
        self.assertEqual((root, src), (None, "flag"))
        self.assertIn("indelible.json", detail)
        # a flag names the root itself: it is not walked up from
        self.assertIsNone(wsmod.find_workspace(flag=str(deep), environ={}, cwd=self.tmp))
        self.assertEqual(wsmod.find_workspace(flag=str(cwd_ws), environ={}, cwd=self.tmp), cwd_ws.resolve())

    def test_cli_discovery_env_and_pointer(self):
        r = run(["subject", "list"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("No indelible workspace found. Run: indelible.py init <path>", r.stderr)
        ws = make_ws(self.tmp, "A")
        r = run(["subject", "list"], env={"INDELIBLE_WORKSPACE": ws})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ielts", r.stdout)
        home = self.tmp / "home2"
        home.mkdir()
        r = run(["init", self.tmp / "ptr-ws", "--pointer", "--timezone", "Europe/Lisbon"],
                env={"HOME": home, "USERPROFILE": home})
        self.assertEqual(r.returncode, 0, r.stderr)
        pointer = home / ".indelible" / "workspace"
        self.assertEqual(pointer.read_text(encoding="utf-8").strip(), str((self.tmp / "ptr-ws").resolve()))
        r = run(["subject", "list"], env={"HOME": home, "USERPROFILE": home})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("No subjects yet", r.stdout)

    def test_subject_resolution_and_ids(self):
        root = make_ws(self.tmp, "A")
        w = wsmod.Workspace(root)
        self.assertEqual(w.resolve_subject().id, "ielts")
        self.assertEqual(w.resolve_subject("ielts").id, "ielts")
        self.assertEqual(w.resolve_subject(cwd=root / "ielts" / "data").id, "ielts")
        with self.assertRaises(Exception):
            w.resolve_subject("nope")
        s = w.subject("ielts")
        self.assertEqual(s.next_error_id(), "E-ielts-0001")
        fio.write_jsonl(s.errors_path, [{"v": 1, "id": "E-ielts-0003"}])
        fio.append_jsonl(s.archive_dir / "errors-2026-09.jsonl", {"v": 1, "id": "E-ielts-0007"})
        fio.append_jsonl(s.attempts_path, {"v": 1, "error_id": "E-ielts-0005"})
        self.assertEqual(s.next_error_id(), "E-ielts-0008")
        self.assertEqual(s.next_session_id(), "S-ielts-0001")
        fio.append_jsonl(s.sessions_path, {"v": 1, "id": "S-ielts-0001"})
        s.write_session_lock({"session_id": "S-ielts-0002"})
        self.assertEqual(s.next_session_id(), "S-ielts-0003")
        self.assertEqual(w.next_block_id("ielts", "2026-10-15"), "B-20261015-ielts-1")
        w.save_blocks([{"v": 1, "id": "B-20261015-ielts-1"}, {"v": 1, "id": "B-20261015-ielts-4"},
                       {"v": 1, "id": "B-20261016-ielts-9"}])
        self.assertEqual(w.next_block_id("ielts", date(2026, 10, 15)), "B-20261015-ielts-5")
        self.assertEqual(w.next_ledger_id(), "L-0001")
        w.append_ledger({"v": 1, "id": "L-0004", "kind": "owed"})
        w.append_ledger({"v": 1, "kind": "status", "ref": "L-0004", "status": "done"})
        self.assertEqual(w.next_ledger_id(), "L-0005")
        self.assertEqual(w.open_ledger_items(), [])

    def test_two_live_subjects_need_a_choice(self):
        root = make_ws(self.tmp, "A")
        r = run(["subject", "add", "spanish", "--title", "Spanish", "--profile", "language"], ws=root)
        self.assertEqual(r.returncode, 0, r.stderr)
        w = wsmod.Workspace(root)
        with self.assertRaises(Exception) as cm:
            w.resolve_subject()
        self.assertIn("ielts", str(cm.exception))
        self.assertIn("spanish", str(cm.exception))


# ==========================================================================
# ladder
# ==========================================================================

class LadderTests(Base):
    def test_add_by_kind(self):
        d = "2026-10-15"
        slip = learning.add({"kind": "slip"}, d)
        self.assertEqual((slip["status"], slip["rung"], slip["next_due"]), ("spacing", 0, "2026-10-16"))
        shaky = learning.add({"kind": "shaky"}, d)
        self.assertEqual((shaky["status"], shaky["rung"], shaky["next_due"]), ("spacing", 1, "2026-10-18"))
        belief = learning.add({"kind": "belief"}, d)
        self.assertEqual((belief["status"], belief["rung"], belief["next_due"]), ("untreated", 0, None))
        with self.assertRaises(ValueError):
            learning.add({"kind": "other"}, d)

    def test_repair(self):
        b = learning.add({"kind": "belief"}, "2026-10-15")
        r = learning.repair(b, "2026-10-15T20:00+01:00")
        self.assertEqual((r["status"], r["rung"], r["next_due"]), ("spacing", 0, "2026-10-16"))
        self.assertEqual(r["repair_at"], "2026-10-15T20:00+01:00")
        self.assertEqual(learning.repair(b, "2026-10-15T07:00+01:00")["next_due"], "2026-10-16")
        self.assertEqual(b["status"], "untreated")  # pure: the input is not changed

    def test_pass_climbs_the_rungs_then_retires(self):
        e = learning.add({"kind": "slip"}, "2026-10-15")
        e = learning.pass_(e, "2026-10-16")
        self.assertEqual((e["rung"], e["next_due"]), (1, "2026-10-19"))
        e = learning.pass_(e, "2026-10-19")
        self.assertEqual((e["rung"], e["next_due"]), (2, "2026-10-26"))
        e = learning.pass_(e, "2026-10-26")
        self.assertEqual((e["rung"], e["next_due"]), (3, "2026-11-16"))
        e = learning.pass_(e, "2026-11-16")
        self.assertEqual((e["status"], e["next_due"]), ("retired", None))
        self.assertEqual(e["passes"], ["2026-10-16", "2026-10-19", "2026-10-26", "2026-11-16"])

    def test_pass_leaves_an_untreated_belief_alone(self):
        # Regression: a repair drill (right, with the fix in view) is no ladder pass.
        b = learning.add({"kind": "belief"}, "2026-10-15")
        out = learning.pass_(b, "2026-10-15", deadline="2026-10-20")
        self.assertEqual((out["status"], out["rung"], out["next_due"], out["passes"]), ("untreated", 0, None, []))
        repaired = learning.repair(out, "2026-10-15T20:00+01:00", deadline="2026-10-20")
        once = learning.pass_(repaired, "2026-10-17", deadline="2026-10-20")
        self.assertNotEqual(once["status"], "retired")  # one real pass is not two days of passes

    def test_fail_by_kind(self):
        b = learning.repair(learning.add({"kind": "belief"}, "2026-10-15"), "2026-10-15T20:00+01:00")
        b = learning.pass_(b, "2026-10-16")
        b = learning.fail(b, "2026-10-19")
        self.assertEqual((b["status"], b["rung"], b["next_due"]), ("untreated", 0, None))
        self.assertEqual(b["fails"], ["2026-10-19"])
        s = learning.pass_(learning.pass_(learning.add({"kind": "slip"}, "2026-10-15"), "2026-10-16"), "2026-10-19")
        s = learning.fail(s, "2026-10-26")
        self.assertEqual((s["status"], s["rung"], s["next_due"]), ("spacing", 0, "2026-10-27"))
        sh = learning.fail(learning.add({"kind": "shaky"}, "2026-10-15"), "2026-10-18")
        self.assertEqual((sh["status"], sh["rung"], sh["next_due"]), ("spacing", 0, "2026-10-19"))
        retired = {"kind": "slip", "status": "retired", "rung": 3, "next_due": None, "passes": [], "fails": []}
        again = learning.fail(retired, "2026-12-01")
        self.assertEqual((again["status"], again["rung"], again["next_due"]), ("reopened", 0, "2026-12-02"))

    def test_deadline_cap(self):
        e = {"kind": "slip", "status": "spacing", "rung": 2, "next_due": "2026-10-20", "passes": [], "fails": []}
        capped = learning.pass_(e, "2026-10-20", deadline="2026-10-30")
        self.assertEqual((capped["rung"], capped["next_due"]), (3, "2026-10-28"))
        uncapped = learning.pass_(e, "2026-10-20")
        self.assertEqual(uncapped["next_due"], "2026-11-10")
        # a cap that would land before tomorrow leaves it at tomorrow
        near = learning.add({"kind": "slip"}, "2026-10-16", deadline="2026-10-17")
        self.assertEqual(near["next_due"], "2026-10-17")
        self.assertEqual(learning.cap_due("2026-11-10", "2026-10-30", "2026-10-20"), date(2026, 10, 28))
        self.assertEqual(learning.cap_due("2026-10-21", "2026-10-30", "2026-10-20"), date(2026, 10, 21))
        self.assertEqual(learning.cap_due("2026-10-25", "2026-10-22", "2026-10-24"), date(2026, 10, 25))
        self.assertIsNone(learning.cap_due(None, "2026-10-30", "2026-10-20"))
        r = learning.repair({"kind": "belief", "status": "untreated"}, "2026-10-20T20:00+01:00", deadline="2026-10-21")
        self.assertEqual(r["next_due"], "2026-10-21")

    def test_short_runway_retirement(self):
        e = {"kind": "slip", "status": "spacing", "rung": 1, "next_due": "2026-10-22",
             "passes": ["2026-10-20"], "fails": []}
        out = learning.pass_(e, "2026-10-22", deadline="2026-11-05")
        self.assertEqual((out["status"], out["next_due"]), ("retired", None))
        same_day = dict(e, passes=["2026-10-22"])
        out = learning.pass_(same_day, "2026-10-22", deadline="2026-11-05")
        self.assertEqual((out["status"], out["rung"], out["next_due"]), ("spacing", 2, "2026-10-29"))
        far = learning.pass_(e, "2026-10-22", deadline="2027-03-01")
        self.assertEqual((far["status"], far["rung"]), ("spacing", 2))
        no_deadline = learning.pass_(e, "2026-10-22")
        self.assertEqual(no_deadline["status"], "spacing")

    def test_is_due(self):
        e = learning.add({"kind": "slip"}, "2026-10-15")
        self.assertFalse(learning.is_due(e, "2026-10-15"))
        self.assertTrue(learning.is_due(e, "2026-10-16"))
        self.assertFalse(learning.is_due(learning.add({"kind": "belief"}, "2026-10-15"), "2026-12-01"))


# ==========================================================================
# session budget
# ==========================================================================

class BudgetTests(Base):
    def test_short_session_row(self):
        b = learning.session_budget(20, "verbal")
        self.assertEqual((b["open_min"], b["close_min"], b["work_fraction"], b["breaks"]), (1, 2, 0.8, 0))
        self.assertEqual(b["asks_budget"], 9)
        self.assertAlmostEqual(b["work_min"], 11.9, places=1)
        self.assertLessEqual(b["work_min"], 0.8 * 20)

    def test_standard_session_row(self):
        b = learning.session_budget(60, "reading")
        self.assertEqual((b["open_min"], b["close_min"], b["work_fraction"], b["breaks"]), (2, 5, 0.7, 0))
        self.assertEqual(b["asks_budget"], 31)
        self.assertEqual(b["close_start_offset_min"], 55)
        self.assertEqual(b["asks_budget"], int(b["work_min"] * 60 // 70))

    def test_long_session_row(self):
        b = learning.session_budget(150, "conceptual")
        self.assertEqual((b["open_min"], b["close_min"], b["work_fraction"], b["breaks"]), (3, 8, 0.6, 1))
        self.assertEqual((b["break_min"], b["break_offsets_min"]), (10, [75]))
        self.assertEqual(b["work_min"], 90.0)
        self.assertEqual(b["asks_budget"], 60)

    def test_band_edges_and_helpers(self):
        self.assertEqual([learning.close_minutes(p) for p in (15, 30, 31, 75, 76, 120)], [2, 2, 5, 5, 8, 8])
        self.assertEqual([learning.break_count(p) for p in (60, 75, 90, 150, 151, 225)], [0, 0, 1, 1, 2, 2])
        self.assertEqual(dates.fmt_iso(learning.close_start("2026-10-15T07:00+01:00", 60)), "2026-10-15T07:55+01:00")
        self.assertEqual(dates.fmt_iso(learning.close_start("2026-10-15T07:00+01:00", 20)), "2026-10-15T07:18+01:00")
        custom = learning.session_budget(60, "reading", pace_s={"reading": 60})
        self.assertGreater(custom["asks_budget"], 31)
        subj = {"topics": [{"id": "T01", "layer": "reading"}, {"id": "T02", "layer": "verbal"},
                           {"id": "T03", "layer": "reading"}, {"id": "T04", "layer": "code", "scope": "out"}]}
        self.assertEqual(learning.dominant_layer(subj), "reading")
        self.assertEqual(learning.dominant_layer({"profile": "code", "topics": []}), "code")


# ==========================================================================
# cold eligibility
# ==========================================================================

T_SERVE = "2026-10-15T08:00+01:00"


def _ago(hours, at=T_SERVE):
    return dates.fmt_iso(dates.parse_iso(at) - timedelta(hours=hours))


class ColdEligibilityTests(Base):
    def exp(self, hours, kind="teach", topic="T04"):
        return {"v": 1, "topic": topic, "at": _ago(hours), "kind": kind}

    def test_window(self):
        for hours, ok in ((30, False), (43, False), (44, True), (49, True), (72, True), (80, False)):
            res = learning.cold_eligibility("T04", T_SERVE, [self.exp(hours)], [])
            self.assertEqual(res["eligible"], ok, "%s h" % hours)
        self.assertAlmostEqual(learning.cold_eligibility("T04", T_SERVE, [self.exp(49)], [])["hours"], 49.0)
        self.assertFalse(learning.is_cold_eligible("T04", T_SERVE, [], []))

    def test_exposure_within_24h_blocks(self):
        exposures = [self.exp(49), self.exp(10, kind="chat")]
        self.assertFalse(learning.is_cold_eligible("T04", T_SERVE, exposures, []))
        # even when the subject window opens earlier than 24 h
        self.assertFalse(learning.is_cold_eligible("T04", T_SERVE, [self.exp(22)], [], window=[20, 96]))
        self.assertTrue(learning.is_cold_eligible("T04", T_SERVE, [self.exp(30)], [], window=[20, 96]))
        # another topic's exposure does not count
        self.assertTrue(learning.is_cold_eligible("T04", T_SERVE, [self.exp(49), self.exp(2, topic="T01")], []))
        # exposures after t are ignored
        later = {"v": 1, "topic": "T04", "at": "2026-10-15T09:00+01:00", "kind": "drill"}
        self.assertTrue(learning.is_cold_eligible("T04", T_SERVE, [self.exp(49), later], []))

    def test_untreated_belief_blocks(self):
        untreated = {"id": "E-ielts-0001", "topic": "T04", "kind": "belief", "status": "untreated"}
        spacing = {"id": "E-ielts-0002", "topic": "T04", "kind": "belief", "status": "spacing"}
        self.assertFalse(learning.is_cold_eligible("T04", T_SERVE, [self.exp(49)], [untreated]))
        self.assertTrue(learning.is_cold_eligible("T04", T_SERVE, [self.exp(49)], [spacing]))

    def test_error_reserve(self):
        e = {"id": "E-ielts-0002", "topic": "T04", "kind": "slip", "status": "spacing", "next_due": "2026-10-15"}
        self.assertTrue(learning.is_error_reserve_eligible(e, T_SERVE, [self.exp(200)], [e]))
        self.assertTrue(learning.is_error_reserve_eligible(e, T_SERVE, [], [e]))
        self.assertFalse(learning.is_error_reserve_eligible(dict(e, next_due="2026-10-16"), T_SERVE, [], [e]))
        self.assertFalse(learning.is_error_reserve_eligible(e, T_SERVE, [self.exp(5, kind="review")], [e]))
        u = dict(e, kind="belief", status="untreated", next_due=None)
        self.assertFalse(learning.is_error_reserve_eligible(u, T_SERVE, [], [u]))

    def test_first_serve(self):
        self.assertTrue(learning.is_first_serve({"taught_at": "2026-10-13T07:00+01:00", "last_cold": None}))
        self.assertFalse(learning.is_first_serve({"taught_at": "2026-10-13T07:00+01:00",
                                                  "last_cold": "2026-10-15T07:00+01:00"}))
        self.assertTrue(learning.is_first_serve({"taught_at": "2026-10-20T07:00+01:00",
                                                 "last_cold": "2026-10-15T07:00+01:00"}))


# ==========================================================================
# levels
# ==========================================================================

DAY0 = datetime(2026, 10, 13, 7, 0, tzinfo=timezone(timedelta(hours=1)))


def att(sheet, verdicts, instrument, day, topic="T04", interval_h=None, least_sure=()):
    """Attempt rows: verdicts like 'rrrw' (r right, h half, w wrong, d don't know)."""
    names = {"r": "right", "h": "half", "w": "wrong", "d": "dont_know", "s": "skip"}
    at = dates.fmt_iso(DAY0 + timedelta(days=day))
    rows = []
    for i, v in enumerate(verdicts):
        rows.append({"v": 1, "sheet": sheet, "item": i + 1, "ask": "%da" % (i + 1), "topic": topic,
                     "layer": "verbal", "instrument": instrument, "cold": instrument == "cold",
                     "interval_h": interval_h, "verdict": names[v], "score": learning.VERDICT_SCORE[names[v]],
                     "check": "filled", "least_sure": i in least_sure, "at": at,
                     "prov": "practice" if instrument == "practice" else "measured"})
    return rows


def level(attempts, topic="T04", window=(44, 72)):
    return learning.compute_levels_from(attempts, {"cold_window_h": list(window), "topics": []})[topic]


class LevelTests(Base):
    def test_level_0(self):
        out = learning.compute_levels_from([], {"topics": [{"id": "T04", "name": "Paraphrase", "layer": "verbal"}]})
        self.assertEqual(out["T04"], {"level": 0, "level_basis": "no evidence yet"})
        low = level(att("ielts-diag-a", "rwwww", "diagnostic", 0))
        self.assertEqual(low["level"], 0)
        self.assertIn("latest measurement", low["level_basis"])

    def test_level_1(self):
        self.assertEqual(level(att("ielts-diag-a", "rrww", "diagnostic", 0))["level"], 1)
        self.assertEqual(level(att("ielts-probe-1", "rhw", "probe", 0))["level"], 1)

    def test_level_2(self):
        lv = level(att("ielts-para-01-drills", "rrrrrw", "practice", 0))
        self.assertEqual(lv["level"], 2)
        self.assertEqual(lv["level_basis"], "practice 5/6 on ielts-para-01-drills (2026-10-13)")
        self.assertEqual(level(att("ielts-para-01-drills", "rrrrww", "practice", 0))["level"], 0)
        # judged per day: two sheets the same day are pooled
        same_day = att("s1", "rrrr", "practice", 0) + att("s2", "wwww", "practice", 0)
        self.assertEqual(level(same_day)["level"], 0)

    def test_level_3p(self):
        lv = level(att("ielts-diag-a", "rrrrw", "diagnostic", 0))
        self.assertEqual(lv["level"], "3p")
        self.assertIn("4/5", lv["level_basis"])
        self.assertEqual(level(att("ielts-diag-a", "rrr", "diagnostic", 0))["level"], 1)  # fewer than 4 asks
        parts = att("ielts-diag-a", "rr", "diagnostic", 0) + att("ielts-diag-b", "rr", "diagnostic", 2)
        self.assertEqual(level(parts)["level"], "3p")  # two parts within 72 h are pooled
        newer = att("ielts-diag-a", "rrrr", "diagnostic", 0) + att("ielts-mock-1", "rwww", "mock", 20)
        self.assertEqual(level(newer)["level"], 1)  # a newer measurement no longer supports 3p

    def test_3p_becomes_3_after_a_cold_pass_within_14_days(self):
        base = att("ielts-diag-a", "rrrr", "diagnostic", 0)
        self.assertEqual(level(base + att("ielts-cold-01", "rrrw", "cold", 5))["level"], 3)
        self.assertEqual(level(base + att("ielts-cold-01", "rrrr", "cold", 20))["level"], "3p")

    def test_level_3(self):
        taught = att("ielts-para-01-drills", "rrrrrr", "practice", 0)
        lv = level(taught + att("ielts-cold-01", "rrrw", "cold", 2, interval_h=49))
        self.assertEqual(lv["level"], 3)
        self.assertIn("at 49 h", lv["level_basis"])
        self.assertEqual(level(taught + att("ielts-cold-01", "rrrr", "cold", 1, interval_h=30))["level"], 2)
        self.assertEqual(level(taught + att("ielts-cold-01", "rrrr", "cold", 3, interval_h=80))["level"], 2)
        self.assertEqual(level(taught + att("ielts-cold-01", "rrww", "cold", 2, interval_h=49))["level"], 2)
        # the subject's own window applies
        self.assertEqual(level(taught + att("c", "rrrr", "cold", 3, interval_h=80), window=(20, 96))["level"], 3)

    def test_level_4(self):
        first = att("ielts-para-01-drills", "rrrrrr", "practice", 0) + att("c1", "rrrr", "cold", 2, interval_h=49)
        lv = level(first + att("c2", "rrrr", "cold", 10, interval_h=240))
        self.assertEqual(lv["level"], 4)
        self.assertIn("8 days after the first", lv["level_basis"])
        self.assertEqual(level(first + att("c2", "rrrr", "cold", 6, interval_h=140))["level"], 3)
        self.assertEqual(level(first + att("c2", "rrrr", "cold", 10, interval_h=5))["level"], 3)

    def test_level_5(self):
        four = (att("d", "rrrrrr", "practice", 0) + att("c1", "rrrr", "cold", 2, interval_h=49)
                + att("c2", "rrrr", "cold", 10, interval_h=240))
        self.assertEqual(level(four + att("ielts-mock-1", "rrrw", "mock", 14))["level"], 5)
        self.assertEqual(level(four + att("ielts-mock-1", "rrww", "mock", 14))["level"], 4)
        early_mock = att("d", "rrrrrr", "practice", 0) + att("ielts-mock-1", "rrrr", "mock", 1)
        self.assertEqual(level(early_mock + att("c1", "rrrr", "cold", 3, interval_h=49)
                               + att("c2", "rrrr", "cold", 11, interval_h=240))["level"], 4)

    def test_least_sure_right_answers_never_count(self):
        taught = att("d", "rrrrrr", "practice", 0)
        # 3 right of 4 would pass; with the least-sure right answer removed it is 2/3
        cold = att("c1", "rrwr", "cold", 2, interval_h=49, least_sure=(3,))
        self.assertEqual(level(taught + cold)["level"], 2)
        self.assertEqual(level(taught + att("c1", "rrwr", "cold", 2, interval_h=49))["level"], 3)
        all_named = att("d", "rrrrrr", "practice", 0, least_sure=range(6))
        lv = level(all_named)
        self.assertEqual(lv["level"], 0)
        self.assertIn("only least-sure questions so far", lv["level_basis"])

    def test_a_miss_named_least_sure_still_counts(self):
        # Regression: naming a miss on the Least-sure line must never hide it from the level.
        taught = att("d", "rrrrrr", "practice", 0)
        cold = att("c1", "rw", "cold", 2, interval_h=49, least_sure=(1,))   # 1 of 2, the miss was named
        lv = level(taught + cold)
        self.assertEqual(lv["level"], 2)
        self.assertNotIn("cold 1/1", lv["level_basis"])
        for v in ("w", "h", "d"):
            diag = att("ielts-diag-a", "r" + v, "diagnostic", 0, least_sure=(1,))
            self.assertIn("diagnostic %s/2" % ("1.5" if v == "h" else "1"), level(diag)["level_basis"])
        # a wrong answer that was the only measured one shows as measured, not as "no evidence"
        only_miss = att("ielts-diag-a", "w", "diagnostic", 0, least_sure=(0,))
        self.assertIn("diagnostic 0/1", level(only_miss)["level_basis"])

    def test_one_cold_question_is_not_enough_for_level_3(self):
        taught = att("d", "rrrrrr", "practice", 0)
        self.assertEqual(level(taught + att("c1", "r", "cold", 2, interval_h=49))["level"], 2)
        self.assertEqual(level(taught + att("c1", "rr", "cold", 2, interval_h=49))["level"], 3)
        self.assertEqual(learning.MIN_COLD_ASKS, 2)

    def test_an_untreated_wrong_idea_holds_the_topic_below_3(self):
        three = att("d", "rrrrrr", "practice", 0) + att("c1", "rrrr", "cold", 2, interval_h=49)
        subject = {"cold_window_h": [44, 72], "topics": []}
        untreated = [{"id": "E-ielts-0005", "topic": "T04", "kind": "belief", "status": "untreated"}]
        lv = learning.compute_levels_from(three, subject, errors=untreated)["T04"]
        self.assertEqual(lv["level"], 2)
        self.assertIn("held at 2", lv["level_basis"])
        self.assertIn("E-ielts-0005", lv["level_basis"])
        repaired = [dict(untreated[0], status="spacing")]
        self.assertEqual(learning.compute_levels_from(three, subject, errors=repaired)["T04"]["level"], 3)
        # a 3p topic stays 3p (it is below 3); another topic's mistake does not count
        other = [dict(untreated[0], topic="T01")]
        self.assertEqual(learning.compute_levels_from(three, subject, errors=other)["T04"]["level"], 3)

    def test_answers_with_the_explanation_in_view_are_no_evidence(self):
        pencils = att("ielts-headings-01-theory", "rrrrr", "practice", 0)
        for row in pencils:
            row["sheet_type"] = "theory"
        lv = level(pencils)
        self.assertEqual(lv["level"], 0)
        for t in ("repair", "example", "external"):
            rows = att("s-" + t, "rrrr", "practice", 0)
            for row in rows:
                row["sheet_type"] = t
            self.assertEqual(level(rows)["level"], 0, t)
        drills = att("s-drills", "rrrr", "practice", 0)
        for row in drills:
            row["sheet_type"] = "drills"
        self.assertEqual(level(drills)["level"], 2)

    def test_contaminated_recheck_questions_are_not_counted(self):
        taught = att("d", "rrrrrr", "practice", 0)
        cold = att("c1", "rrrr", "cold", 2, interval_h=49)
        for row in cold:
            row["contaminated"] = True
        self.assertEqual(level(taught + cold)["level"], 2)

    def test_fewer_than_4_measured_questions_say_why_not_3p(self):
        lv = level(att("ielts-probe-1", "r", "probe", 0))
        self.assertEqual(lv["level"], 1)
        self.assertIn("3p needs at least 4 questions", lv["level_basis"])

    def test_cold_fail_drops_to_2(self):
        three = att("d", "rrrrrr", "practice", 0) + att("c1", "rrrr", "cold", 2, interval_h=49)
        lv = level(three + att("c2", "rwww", "cold", 9, interval_h=200))
        self.assertEqual(lv["level"], 2)
        self.assertIn("cold fail 1/4", lv["level_basis"])
        self.assertIn("back to 2", lv["level_basis"])
        # a middling cold result (50-74%) neither passes nor drops
        self.assertEqual(level(three + att("c2", "rrww", "cold", 9, interval_h=200))["level"], 3)
        # re-taught and passed cold again: back to 3
        again = three + att("c2", "wwww", "cold", 9, interval_h=200) + att("c3", "rrrr", "cold", 12, interval_h=50)
        self.assertEqual(level(again)["level"], 3)

    def test_levels_from_a_subject_folder_and_merge(self):
        root = make_ws(self.tmp, "A")
        s = wsmod.Workspace(root).subject("ielts")
        for row in att("ielts-para-01-drills", "rrrrrw", "practice", 0):
            s.append_attempt(row)
        levels = learning.compute_levels(s.root)
        self.assertEqual(sorted(levels), ["T01", "T02", "T03", "T04"])
        self.assertEqual(levels["T04"]["level"], 2)
        self.assertEqual(levels["T01"]["level"], 0)
        state = {"T04": {"level": 0, "taught_at": "2026-10-13T07:20+01:00", "taught_by": "sheet"}}
        merged = learning.merge_levels(state, levels)
        self.assertEqual(merged["T04"]["taught_at"], "2026-10-13T07:20+01:00")
        self.assertEqual(merged["T04"]["level"], 2)
        self.assertEqual(merged["T01"]["cold_passes"], [])
        self.assertEqual(learning.level_changes(state, levels), [("T04", 0, 2)])
        self.assertEqual(learning.level_rank("3p"), 2.5)


class MetricTests(Base):
    def test_metrics(self):
        rows = (att("c1", "rrwh", "cold", 2, interval_h=49, least_sure=(2,))
                + att("d1", "rwwd", "practice", 3))
        rows[5]["check"] = "missing"
        rows[6]["check"] = "caught"
        acc = learning.accuracy_by_instrument(rows)
        self.assertEqual(sorted(acc), ["cold", "practice"])
        self.assertAlmostEqual(acc["cold"]["value"], 2.5 / 4)
        self.assertAlmostEqual(acc["practice"]["value"], 1 / 4)
        uw = learning.unnamed_wrong_pct(rows)
        self.assertEqual((uw["num"], uw["n"]), (2, 3))
        ls = learning.least_sure_hit_rate(rows)
        self.assertEqual((ls["num"], ls["n"]), (1, 1))
        cov = learning.check_coverage(rows)
        self.assertEqual((cov["num"], cov["n"]), (7, 8))
        self.assertEqual(learning.check_catches(rows), 1)
        r48 = learning.retention_48h(rows)
        self.assertEqual((r48["num"], r48["n"]), (2, 4))
        self.assertIsNone(learning.retention_7d(rows)["value"])
        slips = att("m", "rrrw", "mock", 5, topic="T01")
        slips[3]["mode"] = "C"
        c10 = learning.careless_per_10(slips, {"T01": 3})
        self.assertAlmostEqual(c10["value"], 2.5)
        self.assertIsNone(learning.careless_per_10(slips, {"T01": 2})["value"])


# ==========================================================================
# schema
# ==========================================================================

class SchemaTests(Base):
    def test_every_record_has_an_example_that_validates(self):
        for name in schema.RECORD_NAMES:
            text = schema.describe(name)
            self.assertIn("Example:", text)
            self.assertIn("Fields:", text)
        self.assertEqual(schema.validate_config(schema.example("indelible")), [])
        self.assertEqual(schema.validate_subject(schema.example("subject")), [])
        self.assertEqual(schema.validate_attempt(schema.example("attempt")), [])
        self.assertEqual(schema.validate_error(schema.example("error")), [])
        self.assertEqual(schema.validate_session(schema.example("session")), [])
        self.assertEqual(schema.validate_exposure(schema.example("exposure")), [])
        self.assertEqual(schema.validate_block(schema.example("block")), [])
        self.assertEqual(schema.validate_sheet(schema.example("sheet")), [])
        self.assertEqual(schema.validate_sheetspec(schema.example("sheetspec")), [])
        self.assertEqual(schema.validate_answers(schema.example("answers")), [])
        self.assertEqual(schema.validate_grades(schema.example("grades")), [])
        for row in schema.example("ledger"):
            self.assertEqual(schema.validate_ledger(row), [], row)

    def test_defaults_validate(self):
        self.assertEqual(schema.validate_config(wsmod.default_config()), [])
        subj = wsmod.default_subject()
        subj.update({"id": "ielts", "title": "IELTS Academic"})
        self.assertEqual(schema.validate_subject(subj), [])

    def test_validators_catch_problems(self):
        self.assertTrue(schema.validate_ledger({"v": 1, "id": "L-0001", "kind": "owed", "what": "x", "at": NOW}))
        bad = schema.example("error")
        bad["belief"] = "x" * 121
        self.assertTrue(schema.validate_error(bad))
        spec = schema.example("sheetspec")
        spec["items"][0]["asks"].append({"id": "1a", "label": "again"})
        self.assertTrue(any("used twice" in p for p in schema.validate_sheetspec(spec)))
        self.assertTrue(schema.validate_grades({"asks": [{"ask": "1a", "verdict": "maybe"}]}))


# ==========================================================================
# CLI: doctor, init, subject add, set, schema
# ==========================================================================

class CliSetupTests(Base):
    def test_no_command_and_unknown_workspace(self):
        r = run([])
        self.assertEqual(r.returncode, 2)
        r = run(["subject", "list"], ws=self.tmp / "missing")
        self.assertEqual(r.returncode, 2)
        self.assertIn("No indelible workspace found", r.stderr)

    def test_doctor(self):
        r = run(["doctor", "--quick", "--json"])
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = json.loads(r.stdout)
        self.assertTrue(rep["python_ok"])
        self.assertFalse(rep["workspace"]["found"])
        self.assertTrue(any(x["name"] in ("html", "md") or x["ok"] for x in rep["renderers"]))
        ws = make_ws(self.tmp, "A")
        r = run(["doctor", "--quick", "--json"], ws=ws)
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = json.loads(r.stdout)
        self.assertTrue(rep["workspace"]["found"])
        self.assertTrue(rep["workspace"]["writable"])
        self.assertEqual(rep["timezone"]["workspace"], "Europe/Lisbon")
        self.assertFalse(rep["backend_recorded"])
        r = run(["doctor", "--quick"], ws=ws)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("indelible doctor", r.stdout)
        self.assertIn("Renderers", r.stdout)

    def test_doctor_warns_on_cloud_folder(self):
        root = self.tmp / "Dropbox" / "Study"
        r = run(["init", root, "--timezone", "Europe/Lisbon"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("cloud-synced", r.stdout)
        r = run(["doctor", "--quick", "--json"], ws=root)
        rep = json.loads(r.stdout)
        self.assertEqual(rep["workspace"]["cloud_sync"], "Dropbox")
        self.assertTrue(any("cloud-synced" in w for w in rep["warnings"]))

    def test_init_creates_the_tree_with_defaults(self):
        root = self.tmp / "Study"
        r = run(["init", root, "--timezone", "Europe/Lisbon"])
        self.assertEqual(r.returncode, 0, r.stderr)
        for rel in ("indelible.json", "CLAUDE.md", "ledger.jsonl", "plan/blocks.jsonl", "plan/ics", "views",
                    "reviews", "inbox", ".indelible", ".gitignore"):
            self.assertTrue((root / rel).exists(), rel)
        cfg = json.loads((root / "indelible.json").read_text(encoding="utf-8"))
        self.assertEqual(schema.validate_config(cfg), [])
        self.assertEqual(cfg["timezone"], "Europe/Lisbon")
        self.assertEqual((cfg["session"]["length_min"], cfg["session"]["days_per_week"]), (60, 4))
        self.assertEqual(cfg["time"]["weekly_ceiling_min"], round(1.4 * cfg["time"]["weekly_target_min"]))
        self.assertEqual(cfg["time"]["sleep"], {"bed": "23:00", "wake": "07:00"})
        self.assertEqual(cfg["time"]["windows"][0], {"days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
                                                     "from": "17:00", "to": "21:00"})
        self.assertEqual(cfg["time"]["windows"][1], {"days": ["Sat", "Sun"], "from": "10:00", "to": "18:00"})
        self.assertEqual((cfg["learner"]["tone"], cfg["learner"]["vocab"], cfg["learner"]["chat_math"]),
                         ("B", "plain", "unicode"))
        self.assertEqual(cfg["calendar"]["provider"], "none")
        claude = (root / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(claude.splitlines()), 30)
        self.assertIn(wsmod.MARK_BEGIN, claude)
        self.assertIn(wsmod.MARK_END, claude)
        self.assertIn("brief", claude)
        gi = (root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".indelible/keys/", gi)
        self.assertIn("scans/", gi)
        # a second init is refused and changes nothing
        before = (root / "indelible.json").read_text(encoding="utf-8")
        r = run(["init", root])
        self.assertEqual(r.returncode, 1)
        self.assertIn("already exists", r.stdout)
        self.assertEqual((root / "indelible.json").read_text(encoding="utf-8"), before)

    def test_init_keeps_an_existing_claude_md_and_refuses_the_skill_folder(self):
        root = self.tmp / "existing"
        root.mkdir()
        (root / "CLAUDE.md").write_text("# mine\n", encoding="utf-8")
        r = run(["init", root, "--timezone", "UTC"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((root / "CLAUDE.md").read_text(encoding="utf-8"), "# mine\n")
        inside = SKILL_DIR / "zz-test-workspace"
        try:
            r = run(["init", inside])
            self.assertEqual(r.returncode, 1)
            self.assertIn("outside the skill folder", r.stdout)
            self.assertFalse(inside.exists())
        finally:
            if inside.exists():
                shutil.rmtree(str(inside), ignore_errors=True)

    def test_subject_add(self):
        root = make_ws(self.tmp, "A")
        s = root / "ielts"
        for rel in ("subject.json", "CLAUDE.md", "data/attempts.jsonl", "data/errors.jsonl", "data/sheets.jsonl",
                    "data/exposures.jsonl", "data/sessions.jsonl", "data/topics.json", "data/glossary.jsonl",
                    "views", "notes", "sheets", "scans", "answers", "archive", ".indelible/specs",
                    ".indelible/keys/errors", ".indelible/tmp"):
            self.assertTrue((s / rel).exists(), rel)
        subj = json.loads((s / "subject.json").read_text(encoding="utf-8"))
        self.assertEqual(schema.validate_subject(subj), [])
        self.assertEqual((subj["id"], subj["title"], subj["profile"]), ("ielts", "IELTS Academic", "exam"))
        self.assertEqual(subj["target"]["date"], "2026-12-12")
        self.assertEqual([t["id"] for t in subj["topics"]], ["T01", "T02", "T03", "T04"])
        self.assertEqual(subj["topics"][0]["scope"], "in")
        cfg = json.loads((root / "indelible.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["subjects"][0]["id"], "ielts")
        self.assertEqual(cfg["subjects"][0]["state"], "live")
        claude = (s / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(claude.splitlines()), 80)
        for heading in ("## Target", "## Learner notes", "## Do not calibrate on", "## Overrides of skill defaults",
                        "## Proposed changes", "## Changes"):
            self.assertIn(heading, claude)
        self.assertIn(wsmod.MARK_BEGIN, claude)
        self.assertIn("2026-12-12", claude)
        self.assertNotIn("$", claude)
        self.assertIn("ielts", (root / "CLAUDE.md").read_text(encoding="utf-8"))

        r = run(["subject", "add", "ielts", "--title", "Again", "--profile", "exam"], ws=root)
        self.assertEqual(r.returncode, 1)
        r = run(["subject", "add", "Bad_Id", "--title", "x", "--profile", "exam"], ws=root)
        self.assertEqual(r.returncode, 2)
        r = run(["subject", "add", "plan", "--title", "x", "--profile", "exam"], ws=root)
        self.assertEqual(r.returncode, 2)
        r = run(["subject", "add", "chem", "--title", "Química → ñ", "--profile", "course"], ws=root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Química → ñ", r.stdout)
        chem = json.loads((root / "chem" / "subject.json").read_text(encoding="utf-8"))
        self.assertEqual(chem["title"], "Química → ñ")
        r = run(["subject", "list", "--json"], ws=root)
        self.assertEqual([x["id"] for x in json.loads(r.stdout)], ["ielts", "chem"])

    def test_set(self):
        root = make_ws(self.tmp, "A")
        cfg_path = root / "indelible.json"
        r = run(["set", "root", "session.length_min", "45"], ws=root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("session.length_min: 60 -> 45", r.stdout)
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        self.assertEqual(cfg["session"]["length_min"], 45)
        self.assertEqual(cfg["time"]["weekly_target_min"], 180)  # derived from 45 x 4
        self.assertEqual(cfg["time"]["weekly_ceiling_min"], 252)
        self.assertTrue((root / "indelible.json.bak").exists())

        before = cfg_path.read_text(encoding="utf-8")
        r = run(["set", "root", "session.length_min", "30", "--dry-run"], ws=root)
        self.assertEqual(r.returncode, 0)
        self.assertIn("dry run", r.stdout)
        self.assertEqual(cfg_path.read_text(encoding="utf-8"), before)

        r = run(["set", "root", "learner.tone", '"C"'], ws=root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("Refused", r.stdout)
        r = run(["set", "root", "no.such.path", "1"], ws=root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("unknown path", r.stdout)
        self.assertEqual(cfg_path.read_text(encoding="utf-8"), before)
        r = run(["set", "root", "time.weekly_ceiling_min", "60"], ws=root)
        self.assertEqual(r.returncode, 1)  # below the target
        r = run(["set", "root", "v", "2"], ws=root)
        self.assertEqual(r.returncode, 1)

        r = run(["set", "root", "time.schedule", "on_demand"], ws=root)  # bare word accepted for enums
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run(["set", "root", "subjects.ielts.state", '"paused"'], ws=root)
        self.assertEqual(r.returncode, 0, r.stderr)
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        self.assertEqual(cfg["time"]["schedule"], "on_demand")
        self.assertEqual(cfg["subjects"][0]["state"], "paused")

        r = run(["set", "ielts", "target.date", '"2026-12-10"'], ws=root)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run(["set", "ielts", "topics.T01.layer", '"verbal"'], ws=root)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run(["set", "ielts", "cold_window_h", "[72, 44]"], ws=root)
        self.assertEqual(r.returncode, 1)
        r = run(["set", "ielts", "overrides.+", json.dumps({"rule": "R36", "value": "block_size 4",
                                                            "why": "shorter blocks", "date": "2026-10-12",
                                                            "locked": False})], ws=root)
        self.assertEqual(r.returncode, 0, r.stderr)
        subj = json.loads((root / "ielts" / "subject.json").read_text(encoding="utf-8"))
        self.assertEqual(subj["target"]["date"], "2026-12-10")
        self.assertEqual(subj["topics"][0]["layer"], "verbal")
        self.assertEqual(subj["cold_window_h"], [44, 72])
        self.assertEqual(subj["overrides"][0]["rule"], "R36")
        r = run(["set", "ielts", "id", '"x"'], ws=root)
        self.assertEqual(r.returncode, 1)
        r = run(["set", "nope", "title", '"x"'], ws=root)
        self.assertEqual(r.returncode, 2)
        r = run(["set", "root", "custom.flag", "true", "--force"], ws=root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_schema_command(self):
        for name in schema.RECORD_NAMES:
            r = run(["schema", name])
            self.assertEqual(r.returncode, 0, name + r.stderr)
            self.assertIn("Example:", r.stdout)
        r = run(["schema", "attempt", "--json"])
        self.assertEqual(json.loads(r.stdout)["verdict"], "wrong")
        r = run(["schema", "nope"])
        self.assertEqual(r.returncode, 2)
        r = run(["schema"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("sheetspec", r.stdout)

    def test_personas(self):
        for persona, sid, profile in (("A", "ielts", "exam"), ("B", "spanish", "language"),
                                      ("C", "stats", "course"), ("D", "rust", "code")):
            root = make_ws(self.tmp, persona)
            cfg = json.loads((root / "indelible.json").read_text(encoding="utf-8"))
            self.assertEqual(schema.validate_config(cfg), [], persona)
            subj = json.loads((root / sid / "subject.json").read_text(encoding="utf-8"))
            self.assertEqual(subj["profile"], profile)
            self.assertGreaterEqual(len(subj["topics"]), 2)
            if persona == "D":
                self.assertEqual(cfg["time"]["schedule"], "on_demand")
                self.assertIsNone(subj["target"]["date"])
            if persona == "B":
                self.assertEqual(cfg["session"]["length_min"], 20)
        bare = make_ws(self.tmp / "bare", "C", subject=False)
        self.assertEqual(json.loads((bare / "indelible.json").read_text(encoding="utf-8"))["subjects"], [])


if __name__ == "__main__":
    unittest.main()
