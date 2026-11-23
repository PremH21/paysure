"""SQLite store: credit ledger, seen transactions, shared fake fingerprints, check log (self-labelling)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import datetime

import cv2
import numpy as np
from PIL import Image


def phash(img: Image.Image) -> int:
    """64-bit perceptual hash (DCT based)."""
    g = np.asarray(img.convert("L").resize((32, 32), Image.LANCZOS), dtype=np.float32)
    d = cv2.dct(g)[:8, :8]
    med = np.median(d.flatten()[1:])
    bits = (d.flatten() > med).astype(np.uint8)
    return int("".join(map(str, bits)), 2)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def ref_fingerprint(utr: str, salt: str = "paysure-v1") -> str:
    """Shareable fingerprint of a reference number (no raw number leaves the shop)."""
    return hashlib.sha256((salt + utr).encode()).hexdigest()[:32]


class Store:
    def __init__(self, path: str = "paysure.db"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS seen(utr TEXT PRIMARY KEY, amount REAL, ts REAL);
            CREATE TABLE IF NOT EXISTS credits(
                id INTEGER PRIMARY KEY, amount REAL, utr TEXT, received_at REAL, source TEXT,
                trust INTEGER, flags TEXT, claimed INTEGER DEFAULT 0, balance REAL, payer TEXT);
            CREATE TABLE IF NOT EXISTS orders(
                id TEXT PRIMARY KEY, billed REAL, expected REAL, created REAL, expires REAL, status TEXT, credit_id INTEGER);
            CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
            -- shared fingerprints: kind = 'ref' (hash of reference no.) or 'img' (phash hex)
            CREATE TABLE IF NOT EXISTS fakes(kind TEXT, fp TEXT, reporter TEXT, ts REAL, PRIMARY KEY(kind, fp, reporter));
            CREATE TABLE IF NOT EXISTS checks(id INTEGER PRIMARY KEY, ts REAL, features TEXT, verdict TEXT, label INTEGER);
            """
        )

    # --- seen references (duplicate-use detection) ---
    def utr_seen(self, utr):
        return bool(utr) and self.db.execute("SELECT 1 FROM seen WHERE utr=?", (utr,)).fetchone() is not None

    def mark_seen(self, utr, amount):
        if utr:
            self.db.execute("INSERT OR IGNORE INTO seen VALUES(?,?,?)", (utr, amount, time.time()))
            self.db.commit()

    # --- credit ledger (fed ONLY by trusted channels or by pasted text with low trust) ---
    def add_credit(self, amount, utr, received_at: datetime, source, trust, flags, balance=None, payer=None) -> int:
        cur = self.db.execute(
            "INSERT INTO credits(amount,utr,received_at,source,trust,flags,balance,payer) VALUES(?,?,?,?,?,?,?,?)",
            (amount, utr, received_at.timestamp(), source, trust, json.dumps(flags), balance, payer))
        self.db.commit()
        return cur.lastrowid

    def credits_near(self, amount, since: datetime, until: datetime):
        rows = self.db.execute(
            "SELECT id,amount,utr,received_at,source,trust,flags,claimed FROM credits "
            "WHERE ABS(amount-?)<0.01 AND received_at BETWEEN ? AND ?",
            (amount, since.timestamp(), until.timestamp())).fetchall()
        return [dict(id=r[0], amount=r[1], utr=r[2], received_at=datetime.fromtimestamp(r[3]), source=r[4],
                     trust=r[5], flags=json.loads(r[6]), claimed=bool(r[7])) for r in rows]

    def credits_with_utr(self, utr):
        rows = self.db.execute("SELECT id,amount,utr,received_at,source,trust,flags,claimed FROM credits WHERE utr=?",
                               (utr,)).fetchall()
        return [dict(id=r[0], amount=r[1], utr=r[2], received_at=datetime.fromtimestamp(r[3]), source=r[4],
                     trust=r[5], flags=json.loads(r[6]), claimed=bool(r[7])) for r in rows]

    def claim_credit(self, credit_id):
        self.db.execute("UPDATE credits SET claimed=1 WHERE id=?", (credit_id,))
        self.db.commit()

    def last_balance(self):
        r = self.db.execute("SELECT v FROM kv WHERE k='last_balance'").fetchone()
        return float(r[0]) if r else None

    def set_last_balance(self, bal):
        self.db.execute("INSERT OR REPLACE INTO kv VALUES('last_balance',?)", (str(bal),))
        self.db.commit()

    # --- Neighbourhood Shield ---
    def report_fake(self, utr: str, reporter: str = "local"):
        """Share only a salted hash of the reference number. Image hashes are NOT shared: tests showed a
        perceptual hash cannot tell two different genuine payments from the same app apart."""
        self.db.execute("INSERT OR IGNORE INTO fakes VALUES('ref',?,?,?)", (ref_fingerprint(utr), reporter, time.time()))
        self.db.commit()

    def reporters_for_ref(self, utr) -> int:
        if not utr:
            return 0
        return self.db.execute("SELECT COUNT(DISTINCT reporter) FROM fakes WHERE kind='ref' AND fp=?",
                               (ref_fingerprint(utr),)).fetchone()[0]

    def export_fakes(self, since: float = 0.0):
        return [dict(kind=k, fp=fp, reporter=r, ts=t) for k, fp, r, t in
                self.db.execute("SELECT kind,fp,reporter,ts FROM fakes WHERE ts>?", (since,))]

    def import_fakes(self, rows):
        for r in rows:
            if r.get("kind") == "ref" and isinstance(r.get("fp"), str) and len(r["fp"]) <= 32:
                self.db.execute("INSERT OR IGNORE INTO fakes VALUES(?,?,?,?)",
                                (r["kind"], r["fp"], str(r.get("reporter", "peer"))[:64], float(r.get("ts", time.time()))))
        self.db.commit()

    # --- self-labelling log ---
    def log_check(self, features: dict, verdict: str) -> int:
        cur = self.db.execute("INSERT INTO checks(ts,features,verdict,label) VALUES(?,?,?,NULL)",
                              (time.time(), json.dumps(features), verdict))
        self.db.commit()
        return cur.lastrowid

    def set_label(self, check_id: int, label: int):
        self.db.execute("UPDATE checks SET label=? WHERE id=?", (label, check_id))
        self.db.commit()

    def labelled(self):
        return [(json.loads(f), l) for f, l in self.db.execute("SELECT features,label FROM checks WHERE label IS NOT NULL")]

    # --- credits: extra getters ---
    def get_credit(self, credit_id):
        r = self.db.execute("SELECT id,amount,utr,received_at,source,trust,flags,claimed,payer FROM credits WHERE id=?",
                            (credit_id,)).fetchone()
        if not r:
            return None
        return dict(id=r[0], amount=r[1], utr=r[2], received_at=datetime.fromtimestamp(r[3]), source=r[4],
                    trust=r[5], flags=json.loads(r[6]), claimed=bool(r[7]), payer=r[8])

    def trusted_credits(self, min_trust=2):
        return [(u, datetime.fromtimestamp(t)) for u, t in
                self.db.execute("SELECT utr,received_at FROM credits WHERE trust>=? AND utr IS NOT NULL", (min_trust,))]

    # --- orders (bind each payment to one bill) ---
    def add_order(self, oid, billed, expected, created: datetime, ttl_min):
        self.db.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,NULL)",
                        (oid, billed, expected, created.timestamp(), created.timestamp() + ttl_min * 60, "open"))
        self.db.commit()

    def open_orders(self, now: datetime):
        return [dict(id=i, billed=b, expected=e) for i, b, e in self.db.execute(
            "SELECT id,billed,expected FROM orders WHERE status='open' AND expires>=?", (now.timestamp(),))]

    def close_order(self, oid, credit_id):
        self.db.execute("UPDATE orders SET status='paid', credit_id=? WHERE id=?", (credit_id, oid))
        self.db.commit()

    def has_orders(self) -> bool:
        return self.db.execute("SELECT 1 FROM orders LIMIT 1").fetchone() is not None

    def kv_get(self, k):
        r = self.db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return r[0] if r else None

    def kv_set(self, k, v):
        self.db.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, str(v)))
        self.db.commit()
