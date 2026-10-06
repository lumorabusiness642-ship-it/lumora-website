import os
import sqlite3
import re
from functools import wraps
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

from flask import (
    Flask, abort, flash, g, redirect, render_template,
    request, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from vercel.blob import BlobClient

BASE_DIR = Path(__file__).resolve().parent

# Vercel's deployed filesystem is read-only.
# /tmp is writable during a serverless function invocation.
DATA_DIR = Path("/tmp/lumora_data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "lumora.db"
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    "png", "jpg", "jpeg", "webp", "gif",
    "mp4", "webm", "mov", "avi", "mkv",
    "mp3", "wav", "ogg", "m4a",
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
    "txt", "csv", "zip", "rar", "7z"
}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
VIDEO_EXTENSIONS = {"mp4", "webm", "mov", "avi", "mkv"}
AUDIO_EXTENSIONS = {"mp3", "wav", "ogg", "m4a"}
DOCUMENT_EXTENSIONS = {"pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "txt", "csv"}
ARCHIVE_EXTENSIONS = {"zip", "rar", "7z"}

DEFAULT_SETTINGS = {
    "brand_name": "LUMORA",
    "tagline": "Technology Meets Creativity",
    "hero_title": "Digital experiences built to move your brand forward.",
    "hero_text": "We combine creative design, powerful technology, and digital strategy to create work that looks premium and performs.",
    "hero_image": "",
    "about_title": "Creative thinking. Technical execution.",
    "about_text": "LUMORA is a digital solutions agency focused on video editing, graphic design, digital marketing, and web development.",
    "about_subtext": "Every project is treated as a combination of strategy, design, technology and measurable communication.",
    "services_title": "Services built around your digital goals.",
    "services_text": "Choose a service to open its dedicated portfolio and explore the work behind it.",
    "portfolio_title": "A portfolio that speaks through the work.",
    "process_title": "Simple process. Serious results.",
    "process_text": "From the first conversation to the final delivery, we keep the workflow clear, collaborative and focused.",
    "process_1_title": "Discover", "process_1_text": "Understand your goal, audience and creative direction.",
    "process_2_title": "Design", "process_2_text": "Turn the strategy into a visual and technical direction.",
    "process_3_title": "Build", "process_3_text": "Create, refine and test the final digital experience.",
    "process_4_title": "Deliver", "process_4_text": "Launch polished work that is ready for the real world.",
    "cta_title": "Have a project in mind?",
    "cta_text": "Tell us what you want to build and our team will turn the idea into a polished digital experience.",
    "contact_label": "Project inquiry",
    "contact_note": "We will receive this in the admin panel.",
    "logo_path": "",
    "site_description": "LUMORA — creative technology, digital marketing, design and web development.",
    "meta_keywords": "LUMORA, video editing, graphic design, digital marketing, web development",
    "email": "hello@lumora.com",
    "phone": "+92 300 0000000",
    "whatsapp_number": "+923000000000",
    "address": "Pakistan",
    "facebook": "#",
    "instagram": "#",
    "linkedin": "#",
    "behance": "#",
    "youtube": "#",
    "tiktok": "#",
    "x": "#",
    "footer_text": "Creative technology for modern brands.",
    "analytics_notice": "This website records basic visit and interaction data for security and service improvement. Contact details are only saved when you submit them."
}

DEFAULT_SERVICES = [
    ("Video Editing", "Story-driven edits, reels, YouTube videos, ads, motion graphics and polished post-production.", "video", "01"),
    ("Graphic Designing", "Brand identity, social media creatives, thumbnails, presentations and marketing visuals.", "design", "02"),
    ("Digital Marketing", "Social media strategy, content campaigns, audience growth and performance-focused marketing.", "marketing", "03"),
    ("Web Development", "Fast, responsive and modern websites with thoughtful UX, clean code and scalable structure.", "web", "04"),
]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            icon TEXT NOT NULL DEFAULT 'spark',
            number TEXT NOT NULL DEFAULT '01',
            slug TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            service_id INTEGER NOT NULL,
            image TEXT NOT NULL DEFAULT '',
            project_url TEXT NOT NULL DEFAULT '',
            featured INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS contact_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL,
            email TEXT NOT NULL,
            message TEXT NOT NULL,
            visitor_id TEXT NOT NULL DEFAULT '',
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS visitor_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visitor_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            path TEXT NOT NULL DEFAULT '',
            target TEXT NOT NULL DEFAULT '',
            metadata TEXT NOT NULL DEFAULT '{}',
            ip_address TEXT NOT NULL DEFAULT '',
            user_agent TEXT NOT NULL DEFAULT '',
            referrer TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_visitor_events_created ON visitor_events(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_visitor_events_visitor ON visitor_events(visitor_id);
    """)

    # Lightweight migrations for databases created by older LUMORA versions.
    message_columns = {row[1] for row in db.execute("PRAGMA table_info(contact_messages)").fetchall()}
    if "visitor_id" not in message_columns:
        db.execute("ALTER TABLE contact_messages ADD COLUMN visitor_id TEXT NOT NULL DEFAULT ''")

    columns = {row[1] for row in db.execute("PRAGMA table_info(projects)").fetchall()}
    for name, definition in (("file_path", "TEXT NOT NULL DEFAULT ''"), ("file_name", "TEXT NOT NULL DEFAULT ''"), ("file_kind", "TEXT NOT NULL DEFAULT 'file'")):
        if name not in columns:
            db.execute(f"ALTER TABLE projects ADD COLUMN {name} {definition}")

    # Backfill portfolio metadata for projects created before the multi-file uploader.
    db.execute("UPDATE projects SET file_path = image, file_kind = 'image', file_name = substr(image, instr(image, '/') + 1) WHERE (file_path = '' OR file_path IS NULL) AND image <> ''")

    for key, value in DEFAULT_SETTINGS.items():
        db.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
            (key, value)
        )

    existing = db.execute("SELECT COUNT(*) AS c FROM services").fetchone()["c"]
    if existing == 0:
        for name, desc, icon, number in DEFAULT_SERVICES:
            slug = slugify(name)
            db.execute(
                "INSERT INTO services(name, description, icon, number, slug) VALUES (?, ?, ?, ?, ?)",
                (name, desc, icon, number, slug)
            )

    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")
    admin = db.execute(
        "SELECT id FROM admins WHERE username = ?", (admin_username,)
    ).fetchone()
    if not admin:
        db.execute(
            "INSERT INTO admins(username, password_hash) VALUES (?, ?)",
            (admin_username, generate_password_hash(admin_password))
        )

    db.commit()
    db.close()


def slugify(value):
    value = value.lower().strip()
    chars = []
    last_dash = False
    for ch in value:
        if ch.isalnum():
            chars.append(ch)
            last_dash = False
        elif not last_dash:
            chars.append("-")
            last_dash = True
    return "".join(chars).strip("-") or f"service-{uuid4().hex[:8]}"


@app.template_filter("digits")
def digits(value):
    return re.sub(r"\D", "", value or "")


def setting(key):
    row = get_db().execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else ""


def all_settings():
    rows = get_db().execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def save_settings(form):
    db = get_db()
    for key in DEFAULT_SETTINGS:
        if key in form:
            db.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, form.get(key, "").strip())
            )
    db.commit()


def file_extension(filename):
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


def allowed_file(filename):
    return file_extension(filename) in ALLOWED_EXTENSIONS


def file_kind(filename):
    ext = file_extension(filename)
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    if ext in ARCHIVE_EXTENSIONS:
        return "archive"
    return "file"


def save_upload(file):
    """Upload an admin file to Vercel Blob and return its permanent public URL."""
    if not file or not file.filename:
        return {}

    original = secure_filename(file.filename)
    ext = file_extension(original)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported file type. Allowed: images, video, audio, PDF, Office files, text/CSV and ZIP/RAR/7Z.")

    filename = f"uploads/{uuid4().hex}.{ext}"
    file_bytes = file.read()
    if not file_bytes:
        raise ValueError("The uploaded file is empty.")

    try:
        # Vercel's current Python SDK supports synchronous BlobClient usage.
        # The BLOB_READ_WRITE_TOKEN environment variable is read automatically.
        with BlobClient() as client:
            blob = client.put(
                filename,
                file_bytes,
                access="public",
                content_type=file.mimetype or "application/octet-stream",
                add_random_suffix=False,
            )
    except Exception as exc:
        raise ValueError(f"Could not upload the file to Vercel Blob: {exc}") from exc

    return {
        # Store the public Blob URL directly in SQLite so templates can use it
        # as the image/file source without relying on Vercel's read-only filesystem.
        "path": blob.url,
        "name": original or filename,
        "kind": file_kind(original),
        "ext": ext,
    }


def delete_local_upload(path):
    """Delete a previous Vercel Blob upload. Kept under the old name for compatibility."""
    if not path:
        return

    # New uploads are stored as public Vercel Blob URLs.
    if "blob.vercel-storage.com" in path:
        try:
            # BlobClient.delete() accepts a list of blob URLs.
            with BlobClient() as client:
                client.delete([path])
        except Exception:
            pass
        return

    # Clean up old /tmp uploads if an older project record still points there.
    if path.startswith("uploads/"):
        filename = Path(path).name
        target = UPLOAD_DIR / filename
        if target.exists():
            try:
                target.unlink()
            except OSError:
                pass

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_globals():
    return {
        "site": all_settings(),
        "current_admin": session.get("admin_username"),
    }


def client_ip():
    # Keep the actual connection address; deployments behind a trusted proxy can
    # set ProxyFix if needed. Do not trust arbitrary X-Forwarded-For headers.
    return request.remote_addr or "unknown"


def get_visitor_id():
    visitor_id = request.cookies.get("lumora_visitor")
    if not visitor_id or len(visitor_id) > 80:
        visitor_id = uuid4().hex
    return visitor_id


def record_event(event_type, target="", metadata=None):
    # Do not log admin routes or static assets. This keeps analytics focused on
    # genuine public-site behavior and avoids filling the database with noise.
    if request.path.startswith("/admin") or request.path.startswith("/static"):
        return
    try:
        import json
        db = get_db()
        db.execute(
            "INSERT INTO visitor_events(visitor_id,event_type,path,target,metadata,ip_address,user_agent,referrer) VALUES (?,?,?,?,?,?,?,?)",
            (
                get_visitor_id(), event_type[:50], request.path[:500], target[:500],
                json.dumps(metadata or {}, ensure_ascii=False)[:4000],
                client_ip()[:100], request.headers.get("User-Agent", "")[:1000],
                request.referrer[:1000] if request.referrer else ""
            )
        )
        db.commit()
    except Exception:
        # Analytics must never break the public website.
        pass


@app.after_request
def set_visitor_cookie(response):
    if not request.path.startswith("/admin") and not request.path.startswith("/static"):
        if not request.cookies.get("lumora_visitor"):
            response.set_cookie("lumora_visitor", get_visitor_id(), max_age=60*60*24*365,
                                httponly=True, samesite="Lax")
    return response


@app.before_request
def track_page_view():
    if request.method == "GET" and not request.path.startswith(("/admin", "/static", "/analytics/event")):
        record_event("page_view")


@app.route("/analytics/event", methods=["POST"])
def analytics_event():
    payload = request.get_json(silent=True) or {}
    event_type = str(payload.get("event_type", "interaction"))[:50]
    target = str(payload.get("target", ""))[:500]
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    record_event(event_type, target, metadata)
    return ("", 204)


@app.route("/")
def home():
    db = get_db()
    services = db.execute("SELECT * FROM services ORDER BY id").fetchall()
    projects = db.execute("""
        SELECT p.*, s.name AS service_name, s.slug AS service_slug
        FROM projects p
        JOIN services s ON s.id = p.service_id
        ORDER BY p.featured DESC, p.created_at DESC
    """).fetchall()

    # Build service cards with live portfolio data. Every newly published project
    # automatically becomes visible on its matching service card without needing
    # a separate homepage toggle.
    service_cards = []
    for service in services:
        service_projects = [p for p in projects if p["service_id"] == service["id"]]
        service_cards.append({
            "service": service,
            "projects": service_projects[:3],
            "latest_project": service_projects[0] if service_projects else None,
            "project_count": len(service_projects),
        })

    # Keep the homepage portfolio populated even when the admin does not tick
    # Featured: featured projects are prioritized, then the newest projects.
    featured = projects[:8]
    return render_template("index.html", services=services, projects=projects, featured=featured, service_cards=service_cards)


@app.route("/portfolio/<slug>")
def portfolio(slug):
    db = get_db()
    service = db.execute(
        "SELECT * FROM services WHERE slug = ?", (slug,)
    ).fetchone()
    if not service:
        abort(404)
    record_event("portfolio_view", f"service:{service['slug']}", {"service": service["name"]})
    projects = db.execute("""
        SELECT p.*, s.name AS service_name
        FROM projects p
        JOIN services s ON s.id = p.service_id
        WHERE p.service_id = ?
        ORDER BY p.created_at DESC
    """, (service["id"],)).fetchall()
    return render_template("portfolio.html", service=service, projects=projects)


@app.route("/project/<int:project_id>")
def project_detail(project_id):
    project = get_db().execute("""
        SELECT p.*, s.name AS service_name, s.slug AS service_slug
        FROM projects p
        JOIN services s ON s.id = p.service_id
        WHERE p.id = ?
    """, (project_id,)).fetchone()
    if not project:
        abort(404)
    record_event("project_view", f"project:{project_id}", {"project": project["title"], "service": project["service_name"]})
    return render_template("project.html", project=project)


@app.route("/contact", methods=["POST"])
def contact_message():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    message = request.form.get("message", "").strip()

    # Require a real international-style number with country code.
    phone_digits = digits(phone)
    valid_phone = 8 <= len(phone_digits) <= 15 and phone.strip().startswith("+")
    valid_email = bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email))

    if not phone or not email or not message:
        flash("Please complete your phone number, email and message.", "error")
    elif not valid_phone:
        flash("Please enter your phone number with country code, for example +923001234567.", "error")
    elif not valid_email:
        flash("Please enter a valid email address.", "error")
    elif len(message) > 3000:
        flash("Your message is too long. Please keep it under 3000 characters.", "error")
    else:
        db = get_db()
        db.execute(
            "INSERT INTO contact_messages(name, phone, email, message, visitor_id) VALUES (?, ?, ?, ?, ?)",
            (name[:120], phone[:40], email[:160], message[:3000], get_visitor_id())
        )
        db.commit()
        record_event("contact_submitted", "contact-form", {"has_name": bool(name), "has_phone": bool(phone), "has_email": bool(email)})
        flash("Thanks! Your message has been sent. We will contact you soon.", "success")

    return redirect(url_for("home") + "#contact")


@app.get("/portfolio-file/<int:project_id>")
def portfolio_file(project_id):
    project = get_db().execute("SELECT file_path, file_name FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not project or not project["file_path"]:
        abort(404)

    file_path = project["file_path"]

    # New files live in public Vercel Blob storage. Redirect directly to the
    # permanent Blob URL instead of looking for a local file on Vercel.
    if file_path.startswith("https://"):
        return redirect(file_path)

    # Backward compatibility for old /tmp uploads.
    target = BASE_DIR / "static" / file_path
    if not target.exists():
        abort(404)
    from flask import send_from_directory
    return send_from_directory(target.parent, target.name, as_attachment=True, download_name=project["file_name"] or target.name)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_id"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = get_db().execute(
            "SELECT * FROM admins WHERE username = ?", (username,)
        ).fetchone()

        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]
            next_url = request.args.get("next")
            return redirect(next_url if next_url and next_url.startswith("/") else url_for("admin_dashboard"))

        flash("Invalid username or password.", "error")

    return render_template("admin/login.html")


@app.get("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.get("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    stats = {
        "projects": db.execute("SELECT COUNT(*) AS c FROM projects").fetchone()["c"],
        "services": db.execute("SELECT COUNT(*) AS c FROM services").fetchone()["c"],
        "featured": db.execute("SELECT COUNT(*) AS c FROM projects WHERE featured = 1").fetchone()["c"],
        "messages": db.execute("SELECT COUNT(*) AS c FROM contact_messages").fetchone()["c"],
        "unread_messages": db.execute("SELECT COUNT(*) AS c FROM contact_messages WHERE is_read = 0").fetchone()["c"],
        "visits": db.execute("SELECT COUNT(*) AS c FROM visitor_events WHERE event_type = 'page_view'").fetchone()["c"],
        "visitors": db.execute("SELECT COUNT(DISTINCT visitor_id) AS c FROM visitor_events").fetchone()["c"],
    }
    recent = db.execute("""
        SELECT p.*, s.name AS service_name
        FROM projects p JOIN services s ON s.id = p.service_id
        ORDER BY p.created_at DESC LIMIT 5
    """).fetchall()
    return render_template("admin/dashboard.html", stats=stats, recent=recent)


@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    if request.method == "POST":
        save_settings(request.form)
        logo_file = request.files.get("logo_file")
        hero_file = request.files.get("hero_image_file")
        try:
            if logo_file and logo_file.filename:
                uploaded = save_upload(logo_file)
                if uploaded["kind"] != "image":
                    raise ValueError("Logo must be an image file.")
                old_logo = setting("logo_path")
                delete_local_upload(old_logo)
                get_db().execute("INSERT INTO settings(key,value) VALUES ('logo_path',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (uploaded["path"],))
            if hero_file and hero_file.filename:
                uploaded = save_upload(hero_file)
                if uploaded["kind"] != "image":
                    raise ValueError("Hero image must be an image file.")
                old_hero = setting("hero_image")
                delete_local_upload(old_hero)
                get_db().execute("INSERT INTO settings(key,value) VALUES ('hero_image',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (uploaded["path"],))
            get_db().commit()
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin_settings"))
        flash("Website content updated.", "success")
        return redirect(url_for("admin_settings"))
    return render_template("admin/settings.html", values=all_settings())


@app.route("/admin/services", methods=["GET", "POST"])
@admin_required
def admin_services():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        icon = request.form.get("icon", "spark").strip() or "spark"
        number = request.form.get("number", "").strip() or "01"
        if not name or not description:
            flash("Service name and description are required.", "error")
        else:
            slug = slugify(name)
            try:
                db.execute(
                    "INSERT INTO services(name, description, icon, number, slug) VALUES (?, ?, ?, ?, ?)",
                    (name, description, icon, number, slug)
                )
                db.commit()
                flash("Service added.", "success")
            except sqlite3.IntegrityError:
                flash("A service with that name already exists.", "error")
        return redirect(url_for("admin_services"))

    services = db.execute("SELECT * FROM services ORDER BY id").fetchall()
    return render_template("admin/services.html", services=services)


@app.post("/admin/services/<int:service_id>/edit")
@admin_required
def edit_service(service_id):
    db = get_db()
    service = db.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone()
    if not service:
        abort(404)
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    icon = request.form.get("icon", "spark").strip() or "spark"
    number = request.form.get("number", "").strip() or service["number"]
    if not name or not description:
        flash("Service name and description are required.", "error")
    else:
        new_slug = slugify(name)
        try:
            db.execute("""
                UPDATE services
                SET name=?, description=?, icon=?, number=?, slug=?
                WHERE id=?
            """, (name, description, icon, number, new_slug, service_id))
            db.commit()
            flash("Service updated.", "success")
        except sqlite3.IntegrityError:
            flash("Another service already uses that name.", "error")
    return redirect(url_for("admin_services"))


@app.post("/admin/services/<int:service_id>/delete")
@admin_required
def delete_service(service_id):
    db = get_db()
    project_count = db.execute(
        "SELECT COUNT(*) AS c FROM projects WHERE service_id = ?", (service_id,)
    ).fetchone()["c"]
    if project_count:
        flash("Move or delete this service's projects before deleting the service.", "error")
    else:
        db.execute("DELETE FROM services WHERE id = ?", (service_id,))
        db.commit()
        flash("Service deleted.", "success")
    return redirect(url_for("admin_services"))


@app.get("/admin/projects")
@admin_required
def admin_projects():
    db = get_db()
    projects = db.execute("""
        SELECT p.*, s.name AS service_name
        FROM projects p JOIN services s ON s.id = p.service_id
        ORDER BY p.created_at DESC
    """).fetchall()
    services = db.execute("SELECT * FROM services ORDER BY name").fetchall()
    return render_template("admin/projects.html", projects=projects, services=services)


@app.route("/admin/projects/new", methods=["GET", "POST"])
@admin_required
def new_project():
    db = get_db()
    services = db.execute("SELECT * FROM services ORDER BY name").fetchall()
    if not services:
        flash("Create a service first.", "error")
        return redirect(url_for("admin_services"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        service_id = request.form.get("service_id", "").strip()
        project_url = request.form.get("project_url", "").strip()
        featured = 1 if request.form.get("featured") else 0

        if not title or not service_id:
            flash("Project title and service are required.", "error")
            return render_template("admin/project_form.html", project=None, services=services)

        try:
            uploaded = save_upload(request.files.get("portfolio_file"))
        except ValueError as e:
            flash(str(e), "error")
            return render_template("admin/project_form.html", project=None, services=services)

        path = uploaded.get("path", "")
        kind = uploaded.get("kind", "file")
        image = path if kind == "image" else ""
        db.execute("""
            INSERT INTO projects(title, description, service_id, image, file_path, file_name, file_kind, project_url, featured)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (title, description, service_id, image, path, uploaded.get("name", ""), kind, project_url, featured))
        db.commit()
        flash("Project added.", "success")
        return redirect(url_for("admin_projects"))

    return render_template("admin/project_form.html", project=None, services=services)


@app.route("/admin/projects/<int:project_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_project(project_id):
    db = get_db()
    project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    services = db.execute("SELECT * FROM services ORDER BY name").fetchall()
    if not project:
        abort(404)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        service_id = request.form.get("service_id", "").strip()
        project_url = request.form.get("project_url", "").strip()
        featured = 1 if request.form.get("featured") else 0
        image = project["image"]
        file_path = project["file_path"] or project["image"]
        file_name = project["file_name"]
        file_kind_value = project["file_kind"] or ("image" if project["image"] else "file")

        if not title or not service_id:
            flash("Project title and service are required.", "error")
            return render_template("admin/project_form.html", project=project, services=services)

        try:
            uploaded = save_upload(request.files.get("portfolio_file"))
            if uploaded:
                delete_local_upload(file_path)
                file_path = uploaded["path"]
                file_name = uploaded["name"]
                file_kind_value = uploaded["kind"]
                image = file_path if file_kind_value == "image" else ""
        except ValueError as e:
            flash(str(e), "error")
            return render_template("admin/project_form.html", project=project, services=services)

        db.execute("""
            UPDATE projects
            SET title=?, description=?, service_id=?, image=?, file_path=?, file_name=?, file_kind=?, project_url=?, featured=?
            WHERE id=?
        """, (title, description, service_id, image, file_path, file_name, file_kind_value, project_url, featured, project_id))
        db.commit()
        flash("Project updated.", "success")
        return redirect(url_for("admin_projects"))

    return render_template("admin/project_form.html", project=project, services=services)


@app.post("/admin/projects/<int:project_id>/delete")
@admin_required
def delete_project(project_id):
    db = get_db()
    project = db.execute("SELECT image, file_path FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project:
        delete_local_upload(project["file_path"] or project["image"])
        db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        db.commit()
        flash("Project deleted.", "success")
    return redirect(url_for("admin_projects"))


@app.get("/admin/analytics")
@admin_required
def admin_analytics():
    db = get_db()
    total_events = db.execute("SELECT COUNT(*) AS c FROM visitor_events").fetchone()["c"]
    unique_visitors = db.execute("SELECT COUNT(DISTINCT visitor_id) AS c FROM visitor_events").fetchone()["c"]
    page_views = db.execute("SELECT COUNT(*) AS c FROM visitor_events WHERE event_type='page_view'").fetchone()["c"]
    interactions = db.execute("SELECT COUNT(*) AS c FROM visitor_events WHERE event_type NOT IN ('page_view')").fetchone()["c"]
    recent_events = db.execute("""
        SELECT * FROM visitor_events ORDER BY id DESC LIMIT 150
    """).fetchall()
    popular_pages = db.execute("""
        SELECT path, COUNT(*) AS views FROM visitor_events
        WHERE event_type='page_view' GROUP BY path ORDER BY views DESC LIMIT 10
    """).fetchall()
    recent_visitors = db.execute("""
        SELECT visitor_id, MAX(created_at) AS last_seen, COUNT(*) AS actions,
               MAX(ip_address) AS ip_address, MAX(user_agent) AS user_agent, MAX(referrer) AS referrer
        FROM visitor_events GROUP BY visitor_id ORDER BY last_seen DESC LIMIT 50
    """).fetchall()
    return render_template("admin/analytics.html", total_events=total_events, unique_visitors=unique_visitors,
                           page_views=page_views, interactions=interactions, recent_events=recent_events,
                           popular_pages=popular_pages, recent_visitors=recent_visitors)


@app.post("/admin/analytics/clear")
@admin_required
def clear_analytics():
    get_db().execute("DELETE FROM visitor_events")
    get_db().commit()
    flash("Visitor analytics cleared.", "success")
    return redirect(url_for("admin_analytics"))


@app.get("/admin/messages")
@admin_required
def admin_messages():
    db = get_db()
    messages = db.execute("SELECT * FROM contact_messages ORDER BY is_read ASC, created_at DESC").fetchall()
    return render_template("admin/messages.html", messages=messages)


@app.post("/admin/messages/<int:message_id>/read")
@admin_required
def mark_message_read(message_id):
    db = get_db()
    db.execute("UPDATE contact_messages SET is_read = 1 WHERE id = ?", (message_id,))
    db.commit()
    return redirect(url_for("admin_messages"))


@app.post("/admin/messages/<int:message_id>/unread")
@admin_required
def mark_message_unread(message_id):
    db = get_db()
    db.execute("UPDATE contact_messages SET is_read = 0 WHERE id = ?", (message_id,))
    db.commit()
    return redirect(url_for("admin_messages"))


@app.post("/admin/messages/<int:message_id>/delete")
@admin_required
def delete_message(message_id):
    db = get_db()
    db.execute("DELETE FROM contact_messages WHERE id = ?", (message_id,))
    db.commit()
    flash("Message deleted.", "success")
    return redirect(url_for("admin_messages"))


@app.route("/admin/password", methods=["GET", "POST"])
@admin_required
def admin_password():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        admin = get_db().execute(
            "SELECT * FROM admins WHERE id = ?", (session["admin_id"],)
        ).fetchone()

        if not check_password_hash(admin["password_hash"], current):
            flash("Current password is incorrect.", "error")
        elif len(new_password) < 8:
            flash("New password must be at least 8 characters.", "error")
        elif new_password != confirm:
            flash("New passwords do not match.", "error")
        else:
            get_db().execute(
                "UPDATE admins SET password_hash=? WHERE id=?",
                (generate_password_hash(new_password), session["admin_id"])
            )
            get_db().commit()
            flash("Password changed successfully.", "success")
            return redirect(url_for("admin_dashboard"))

    return render_template("admin/password.html")


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/admin"):
        return render_template("admin/error.html", code=404, message="Page not found."), 404
    return render_template("error.html", code=404, message="That page does not exist."), 404


# Initialize the database for both local runs and WSGI deployments.
init_db()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
