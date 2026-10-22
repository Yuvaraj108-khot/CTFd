# CTFd cPanel Deployment Guide

This guide explains how to deploy CTFd onto a cPanel web hosting environment using **Setup Python App** (Phusion Passenger) and **MySQL**.

---

## 1. Prerequisites

- A cPanel hosting account with **Setup Python App** (CloudLinux Python Selector).
- Python **3.9**, **3.10**, or **3.11** available in cPanel.
- Access to **MySQL Database Wizard** and **File Manager** (or SSH/Terminal).

---

## 2. Step-by-Step Deployment Instructions

### Step 1: Create a MySQL Database
1. In cPanel, navigate to **MySQL Databases** (or **MySQL Database Wizard**).
2. Create a new database (e.g., `cpaneluser_ctfd`).
3. Create a new MySQL user (e.g., `cpaneluser_ctfadmin`) with a secure password.
4. Add the user to the database and grant **ALL PRIVILEGES**.
5. Note down your full database name, username, and password.

---

### Step 2: Upload the Distribution Files
1. Open **File Manager** in cPanel.
2. In your home directory (`/home/username/`), create a new folder named `ctfd` (recommended to keep it outside `public_html` for security, or inside if required by your host).
3. Upload `ctfd_cpanel_dist.zip` into `/home/username/ctfd`.
4. Right-click the uploaded zip file and click **Extract**.
5. Verify the files are extracted into the `ctfd` directory (so that `passenger_wsgi.py` and `CTFd` are directly under `/home/username/ctfd/`).

---

### Step 3: Configure "Setup Python App" in cPanel
1. In cPanel, find and open **Setup Python App**.
2. Click **Create Application**.
3. Fill in the following fields:
   - **Python version**: Select **3.10** or **3.11** (recommended).
   - **Application root**: `ctfd` (the directory where you extracted the files).
   - **Application URL**: Select your domain or subdomain (e.g., `ctf.yourdomain.com`).
   - **Application startup file**: `passenger_wsgi.py`
   - **Application Entry point**: `application`
4. Click **Create** in the top-right corner.

---

### Step 4: Configure Database & Settings in `CTFd/config.ini`
1. In **File Manager**, navigate to `ctfd/CTFd/` and edit `config.ini`.
2. Locate the `[server]` section and set your MySQL connection string under `DATABASE_URL`:
   ```ini
   DATABASE_URL = mysql+pymysql://<DB_USER>:<DB_PASSWORD>@localhost/<DB_NAME>?charset=utf8mb4
   ```
   *Replace `<DB_USER>`, `<DB_PASSWORD>`, and `<DB_NAME>` with your actual cPanel MySQL credentials.*

3. Under the `[server]` section, ensure `SECRET_KEY` is either left blank (CTFd will auto-generate one) or provide a 64-character random string.

4. Under `[optional]`, ensure:
   ```ini
   REVERSE_PROXY = true
   SERVER_SENT_EVENTS = false
   ```

5. Save the file.

---

### Step 5: Install Python Dependencies
You can install dependencies through either the cPanel web interface or the Terminal.

#### Option A: Via cPanel Web UI
1. In **Setup Python App**, scroll down to the **Configuration files** section.
2. Type `requirements.txt` in the input box and click **Add**.
3. Click the **Run Pip Install** button next to `requirements.txt`.
4. Wait for the installation to finish.

#### Option B: Via cPanel Terminal / SSH (Recommended)
1. At the top of your app settings in **Setup Python App**, copy the virtual environment command shown in the box (for example: `source /home/username/virtualenv/ctfd/3.11/bin/activate && cd /home/username/ctfd`).
2. Open the **Terminal** tool in cPanel and paste that command.
3. Run:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

### Step 6: Verify File Permissions
Ensure the runtime directories are writable by the web server process:
```bash
chmod -R 755 .data CTFd/uploads CTFd/logs
```

---

### Step 7: Restart and Complete Setup
1. In **Setup Python App**, click **Restart** on your application.
2. Open your website in a browser (`https://ctf.yourdomain.com`).
3. You will see the **CTFd Setup Wizard** asking for:
   - CTF Name & Description
   - Admin Username, Email, and Password
   - User mode (Teams or Users)
4. Complete the wizard and your CTFd platform is live!

---

## 3. Troubleshooting

- **500 Internal Server Error**:
  - The included `passenger_wsgi.py` contains a built-in diagnostic screen that will display the exact error traceback in your browser if startup fails (e.g., incorrect database credentials or missing package).
- **Database Connection Refused**:
  - Ensure the MySQL user has privileges on the database.
  - Verify `localhost` is used for the database host.
- **Static Assets or Images Not Loading**:
  - Pre-compiled assets are located in `CTFd/themes/core/static` and `CTFd/themes/admin/static`. Passenger serves these via Flask. If using Apache to serve static files directly, you can map `/themes/core/static` to the filesystem path in `.htaccess`.
- **Changes Not Taking Effect**:
  - Click **Restart** in the **Setup Python App** panel or touch `tmp/restart.txt`:
    ```bash
    mkdir -p tmp && touch tmp/restart.txt
    ```
