# MediTrack — Hospital Equipment & Inventory Management System

A Flask + MySQL application for a hospital biomedical engineering department
to track medical equipment (ventilators, infusion pumps, defibrillators,
monitors) across departments, along with their maintenance history.

Built for the MentorX Academy Cloud Computing Workshop capstone: deployed on
your own AWS infrastructure with EC2, RDS, Gunicorn, and Nginx.

## 1. Project structure

```
MediTrack/
├── .idea/                     # PyCharm project metadata (safe to ignore/delete)
├── static/
│   └── css/style.css          # App styling
├── templates/                 # Jinja2 templates
│   ├── base.html
│   ├── dashboard.html
│   ├── index.html              # Equipment list + filters
│   ├── add_equipment.html
│   ├── edit_equipment.html     # Update status / department
│   ├── equipment_detail.html   # Maintenance history for one item
│   └── add_maintenance.html
├── deployment/
│   ├── schema.sql              # Manual table creation (alternative to init_db())
│   ├── seed_data.sql           # Sample rows incl. one overdue record
│   ├── meditrack.service       # systemd unit for Gunicorn
│   └── nginx_meditrack.conf    # Nginx reverse-proxy config
├── app.py                      # Flask application (routes + DB logic)
├── requirements.txt
├── .env                        # Local secrets — gitignored, never commit
├── .env.example                # Template showing required variable names
├── .gitignore
└── README.md
```

## 2. Data model

**equipment**

| Field | Type |
|---|---|
| equipment_id | INT, PK, AUTO_INCREMENT |
| equipment_name | VARCHAR(100) |
| serial_number | VARCHAR(50), UNIQUE |
| department | VARCHAR(100) |
| purchase_date | DATE |
| status | ENUM('Active','Under Maintenance','Decommissioned') |

**maintenance_log** (many-to-one with equipment)

| Field | Type |
|---|---|
| log_id | INT, PK, AUTO_INCREMENT |
| equipment_id | INT, FK → equipment.equipment_id |
| maintenance_date | DATE |
| technician_name | VARCHAR(100) |
| issue_reported | TEXT |
| resolution_notes | TEXT |
| next_due_date | DATE |

An item is considered **overdue** when its most recently logged
`next_due_date` is earlier than today.

## 3. Local development setup

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # then edit .env with your real RDS values
```

Create the database — either let the app do it, or run the SQL script yourself:

```bash
# Option A: automatic, runs on every app start (safe — uses CREATE TABLE IF NOT EXISTS)
python app.py

# Option B: manual
mysql -h <DB_HOST> -u <DB_USER> -p < deployment/schema.sql
mysql -h <DB_HOST> -u <DB_USER> -p meditrack < deployment/seed_data.sql   # optional sample data
```

Visit `http://127.0.0.1:5000`.

## 4. Provisioning Amazon RDS (MySQL)

1. RDS console → **Create database** → MySQL → `db.t3.micro` (free-tier eligible).
2. Set a master username/password — you'll put these in `.env`, never in code.
3. **Security group**: create one that allows inbound **port 3306** only from
   your EC2 instance's security group (not `0.0.0.0/0`).
4. Once available, copy the endpoint into `DB_HOST` in your `.env`.
5. Create the schema with `deployment/schema.sql` (see above) or let
   `init_db()` create it on first run.

## 5. Launching EC2

1. Launch a **fresh Ubuntu** instance (don't reuse an earlier CRUD project instance).
2. Security group: **SSH (22)** from your IP only, **HTTP (80)** from anywhere.
3. SSH in and install prerequisites:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git nginx
```

## 6. Pushing to GitHub and cloning onto EC2

Locally:

```bash
git init
git add .
git commit -m "Initial MediTrack commit"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

`.gitignore` already excludes `venv/`, `__pycache__/`, and `.env` — double
check `git status` before your first commit to be sure no secrets are staged.

On the EC2 instance:

```bash
git clone <your-repo-url>
cd MediTrack
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env        # fill in your real RDS credentials here, directly on the server
```

## 7. Gunicorn — test manually first

```bash
source venv/bin/activate
gunicorn --bind 127.0.0.1:8000 app:app
```

Confirm it responds:

```bash
curl http://127.0.0.1:8000/dashboard
```

Stop it with `Ctrl+C` once confirmed, then move to the managed service below.

## 8. Gunicorn as a systemd service

```bash
sudo cp deployment/meditrack.service /etc/systemd/system/meditrack.service
sudo systemctl daemon-reload
sudo systemctl enable meditrack
sudo systemctl start meditrack
sudo systemctl status meditrack
```

`deployment/meditrack.service` assumes the repo is cloned to
`/home/ubuntu/MediTrack` under the `ubuntu` user — edit `User`,
`WorkingDirectory`, and the venv path if yours differs.

## 9. Nginx reverse proxy

First confirm nothing else is already bound to port 80:

```bash
sudo ss -tlnp | grep :80
```

Then:

```bash
sudo cp deployment/nginx_meditrack.conf /etc/nginx/sites-available/meditrack
sudo ln -s /etc/nginx/sites-available/meditrack /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

The app should now be reachable at `http://<your-ec2-public-ip>` with no
port number.

## 10. Verifying against the evaluation checklist

| Check | How to verify |
|---|---|
| App loads with no port number | Visit `http://<ec2-ip>` in a browser |
| New equipment appears in list view | Add via the UI, confirm on `/equipment` |
| Maintenance log shows correct history | Add a log entry, confirm on the equipment detail page |
| Dashboard flags at least one overdue item | Run `deployment/seed_data.sql`, or log a record with a past `next_due_date` |
| Gunicorn service is active | `sudo systemctl status meditrack` should show `active (running)` |
| Reboot recovers automatically | `sudo reboot`, then revisit the site after it comes back up |
| No credentials in GitHub | `git log -p -- .env` should return nothing; `.env` should not appear in `git ls-files` |

## 11. Debugging

When something doesn't come up, check the logs in this order:

```bash
sudo journalctl -u meditrack -n 50 --no-pager   # Gunicorn / app errors
sudo tail -n 50 /var/log/nginx/error.log        # Nginx-level errors
sudo nginx -t                                   # config syntax check
```

## 12. Stretch goal — JSON feed

`GET /api/overdue` returns the same overdue list as the dashboard, as JSON,
so a separate alerting service could poll it.

```bash
curl http://127.0.0.1:8000/api/overdue
```
