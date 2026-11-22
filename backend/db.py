import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from .config import DB_PATH, DEFAULTS

WRITE_LOCK = threading.RLock()

@contextmanager
def connect():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    try:
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.close()

def init():
    with WRITE_LOCK, connect() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY, applied_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT, sha256 TEXT UNIQUE,
            url TEXT, kind TEXT NOT NULL, duration REAL NOT NULL DEFAULT 0, width INTEGER DEFAULT 0,
            height INTEGER DEFAULT 0, fps REAL DEFAULT 0, size INTEGER DEFAULT 0, has_audio INTEGER DEFAULT 0,
            thumbnail TEXT, status TEXT DEFAULT 'Imported', metadata TEXT DEFAULT '{}', created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS rights_metadata(source_id TEXT PRIMARY KEY REFERENCES sources(id),
            status TEXT NOT NULL, license TEXT NOT NULL, origin TEXT NOT NULL, confirmed_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS transcripts(source_id TEXT PRIMARY KEY REFERENCES sources(id),
            model TEXT NOT NULL, language TEXT, text TEXT NOT NULL, data TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS analysis(id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
            cache_key TEXT UNIQUE NOT NULL, provider TEXT NOT NULL, data TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS clips(id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
            title TEXT NOT NULL, start REAL NOT NULL, end REAL NOT NULL, score REAL NOT NULL,
            provider TEXT NOT NULL, approved INTEGER DEFAULT 0, data TEXT NOT NULL,
            render_path TEXT, render_revision INTEGER, revision INTEGER DEFAULT 1, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS scores(clip_id TEXT PRIMARY KEY REFERENCES clips(id), data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS segments(id TEXT PRIMARY KEY, clip_id TEXT NOT NULL REFERENCES clips(id),
            position INTEGER NOT NULL, start REAL NOT NULL, end REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS projects(clip_id TEXT PRIMARY KEY REFERENCES clips(id), data TEXT NOT NULL, updated_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS deleted_clips(id TEXT PRIMARY KEY,deleted_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, source_id TEXT REFERENCES sources(id), clip_id TEXT REFERENCES clips(id),
            kind TEXT NOT NULL, status TEXT NOT NULL, stage TEXT DEFAULT 'Queued', progress REAL DEFAULT 0,
            payload TEXT NOT NULL, checkpoints TEXT DEFAULT '{}', error TEXT, logs TEXT DEFAULT '[]',
            created_at REAL NOT NULL, updated_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS render_tasks(job_id TEXT PRIMARY KEY REFERENCES jobs(id), plan TEXT NOT NULL, qc TEXT);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS usage(id TEXT PRIMARY KEY, model TEXT NOT NULL, input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL, estimated_cost REAL, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS music_usage(id TEXT PRIMARY KEY, model TEXT NOT NULL, seconds REAL NOT NULL,
            status TEXT NOT NULL, job_id TEXT, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS publications(id TEXT PRIMARY KEY,clip_id TEXT REFERENCES clips(id) ON DELETE SET NULL,
            revision INTEGER NOT NULL,channel_id TEXT NOT NULL,title TEXT NOT NULL,render_path TEXT NOT NULL,
            sha256 TEXT NOT NULL,plan TEXT NOT NULL,metadata TEXT,profile TEXT NOT NULL,publish_at REAL,
            state TEXT NOT NULL,youtube_id TEXT,job_id TEXT NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL,error TEXT,
            UNIQUE(channel_id,sha256));
        CREATE TABLE IF NOT EXISTS montage_projects(id TEXT PRIMARY KEY, title TEXT NOT NULL, data TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1, render_path TEXT, render_revision INTEGER,
            created_at REAL NOT NULL, updated_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS montage_media(id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
            path TEXT NOT NULL, sha256 TEXT UNIQUE NOT NULL, duration REAL NOT NULL, width INTEGER DEFAULT 0,
            height INTEGER DEFAULT 0, has_audio INTEGER DEFAULT 0, thumbnail TEXT, created_at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS publications_schedule ON publications(channel_id,publish_at);
        CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status,kind,created_at);
        CREATE INDEX IF NOT EXISTS clips_source ON clips(source_id);
        ''')
        c.execute('INSERT OR IGNORE INTO migrations VALUES(1,?)', (time.time(),))
        for key, value in DEFAULTS.items():
            c.execute('INSERT OR IGNORE INTO settings VALUES(?,?)', (key, json.dumps(value)))

def rows(sql, params=()):
    with connect() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]

def one(sql, params=()):
    r = rows(sql, params)
    return r[0] if r else None

def execute(sql, params=()):
    with WRITE_LOCK, connect() as c:
        return c.execute(sql, params).rowcount

def settings():
    return {r['key']: json.loads(r['value']) for r in rows('SELECT * FROM settings')}

def uid():
    return uuid.uuid4().hex

def dump(value):
    return json.dumps(value, ensure_ascii=False)

def job_update(job_id, **fields):
    fields['updated_at'] = time.time()
    execute('UPDATE jobs SET ' + ','.join(f'{k}=?' for k in fields) + ' WHERE id=?', (*fields.values(), job_id))

def log(job_id, message):
    from .config import redact
    with WRITE_LOCK, connect() as c:
        r = c.execute('SELECT logs FROM jobs WHERE id=?', (job_id,)).fetchone()
        if r:
            logs = json.loads(r['logs'])[-79:] + [{'time': time.time(), 'message': redact(message)}]
            c.execute('UPDATE jobs SET logs=?,updated_at=? WHERE id=?', (dump(logs), time.time(), job_id))
