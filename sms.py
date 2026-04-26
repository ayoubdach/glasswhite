from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from flask_cors import CORS
import subprocess, sqlite3, datetime, secrets, hashlib, time, threading
import re

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
CORS(app)

API_KEY = "GlasswhiteUltimate2026"

# Database setup
def init_db():
    conn = sqlite3.connect('sms_complete.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT, number TEXT, message TEXT, status TEXT, 
                  timestamp DATETIME, sender_ip TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS contacts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT, name TEXT, number TEXT, group_name TEXT, created DATETIME)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE, password_hash TEXT, created DATETIME, last_login DATETIME)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS scheduled
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT, number TEXT, message TEXT, schedule_time DATETIME, status TEXT)''')
    
    default_users = ['admin', 'user1', 'user2', 'user3', 'user4', 'user5']
    for user in default_users:
        c.execute("SELECT * FROM users WHERE username = ?", (user,))
        if not c.fetchone():
            c.execute("INSERT INTO users (username, created) VALUES (?,?)", (user, datetime.datetime.now()))
    
    conn.commit()
    conn.close()

init_db()

# Send SMS function
def send_sms(number, message, retry_count=3):
    number = re.sub(r'\s+', '', number)
    if not number.startswith('+'):
        number = '+' + number
    
    for attempt in range(retry_count):
        try:
            result = subprocess.run(['termux-sms-send', '-n', number, message], timeout=30, capture_output=True, text=True)
            if result.returncode == 0:
                time.sleep(2)
                return True, "Sent"
            else:
                if attempt < retry_count - 1:
                    time.sleep(2)
                    continue
                return False, f"Failed"
        except:
            if attempt < retry_count - 1:
                time.sleep(2)
                continue
            return False, "Error"
    return False, "Unknown"

# Scheduler thread
def scheduler_worker():
    while True:
        try:
            now = datetime.datetime.now()
            conn = sqlite3.connect('sms_complete.db')
            c = conn.cursor()
            c.execute("SELECT id, number, message FROM scheduled WHERE schedule_time <= ? AND status = 'pending'", (now,))
            pending = c.fetchall()
            for msg_id, number, message in pending:
                success, _ = send_sms(number, message)
                c.execute("UPDATE scheduled SET status = ? WHERE id = ?", ('sent' if success else 'failed', msg_id))
                c.execute("INSERT INTO messages (username, number, message, status, timestamp) VALUES (?,?,?,?,?)",
                          ('scheduled', number, message, 'Sent' if success else 'Failed', now))
                conn.commit()
                time.sleep(8)
            conn.close()
        except:
            pass
        time.sleep(30)

threading.Thread(target=scheduler_worker, daemon=True).start()

# HTML Templates
HOME_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <title>SMS Gateway</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container { max-width: 500px; width: 100%; }
        .card {
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
        }
        h1 { color: #333; margin-bottom: 10px; }
        .subtitle { color: #666; margin-bottom: 30px; }
        .user-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin: 30px 0;
        }
        .user-btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 20px;
            border-radius: 15px;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.2s;
        }
        .user-btn:hover { transform: translateY(-3px); }
        .admin-btn { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
        .footer { margin-top: 20px; color: #999; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>📱 SMS Gateway</h1>
            <p class="subtitle">Select your account</p>
            <div class="user-grid">
                <button class="user-btn admin-btn" onclick="selectUser('admin')">👑 Admin</button>
                <button class="user-btn" onclick="selectUser('user1')">👤 User 1</button>
                <button class="user-btn" onclick="selectUser('user2')">👤 User 2</button>
                <button class="user-btn" onclick="selectUser('user3')">👤 User 3</button>
                <button class="user-btn" onclick="selectUser('user4')">👤 User 4</button>
                <button class="user-btn" onclick="selectUser('user5')">👤 User 5</button>
            </div>
            <div class="footer">Your password is private. Never share it.</div>
        </div>
    </div>
    <script>
        function selectUser(username) {
            window.location.href = '/login/' + username;
        }
    </script>
</body>
</html>
'''

LOGIN_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Login - {{ username }}</title>
    <style>
        body{background:linear-gradient(135deg,#667eea,#764ba2);font-family:Arial;display:flex;justify-content:center;align-items:center;height:100vh;}
        .card{background:white;padding:40px;border-radius:20px;width:350px;text-align:center;}
        input{width:100%;padding:12px;margin:10px 0;border:2px solid #ddd;border-radius:10px;}
        button{width:100%;background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:12px;border:none;border-radius:10px;cursor:pointer;}
        .error{color:red;margin:10px;}
        .info{color:green;margin:10px;}
    </style>
</head>
<body>
    <div class="card">
        <h2>🔐 Login</h2>
        <p><strong>{{ username }}</strong></p>
        {% if not has_password %}<div class="info">✨ First time! Create your password.</div>{% endif %}
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST">
            <input type="password" name="password" placeholder="Enter password" required>
            <button type="submit">{% if not has_password %}Create Account{% else %}Login{% endif %}</button>
        </form>
        <a href="/">← Back</a>
    </div>
</body>
</html>
'''

DASHBOARD_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <title>SMS Gateway - {{ username }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .card { border-radius: 15px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); margin-bottom: 20px; border: none; }
        .card-header { background: white; border-bottom: 2px solid #f0f0f0; font-weight: bold; }
        .btn-gradient { background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; }
        .btn-gradient:hover { transform: translateY(-2px); color: white; }
        .stat-card { background: white; border-radius: 15px; padding: 20px; text-align: center; margin-bottom: 20px; }
        .stat-value { font-size: 32px; font-weight: bold; color: #667eea; }
        .nav-tabs .nav-link.active { background: linear-gradient(135deg, #667eea, #764ba2); color: white; }
        .delay-slider { width: 100%; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <h2><i class="fas fa-sms"></i> SMS Gateway Pro</h2>
                        <p>Welcome, <strong>{{ username }}</strong>!</p>
                    </div>
                    <div class="col-md-6 text-end">
                        <span class="badge bg-primary"><i class="fas fa-user"></i> {{ username }}</span>
                        <a href="/logout" class="btn btn-danger btn-sm ms-2"><i class="fas fa-sign-out-alt"></i> Logout</a>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="row">
            <div class="col-md-3"><div class="stat-card"><i class="fas fa-envelope fa-2x"></i><div class="stat-value" id="totalSMS">0</div><div>Total SMS</div></div></div>
            <div class="col-md-3"><div class="stat-card"><i class="fas fa-check-circle fa-2x"></i><div class="stat-value" id="successRate">0%</div><div>Success Rate</div></div></div>
            <div class="col-md-3"><div class="stat-card"><i class="fas fa-address-book fa-2x"></i><div class="stat-value" id="myContacts">0</div><div>Contacts</div></div></div>
            <div class="col-md-3"><div class="stat-card"><i class="fas fa-clock fa-2x"></i><div class="stat-value" id="scheduledCount">0</div><div>Scheduled</div></div></div>
        </div>
        
        <ul class="nav nav-tabs mb-3">
            <li class="nav-item"><a class="nav-link active" data-bs-toggle="tab" href="#sendTab"><i class="fas fa-paper-plane"></i> Send SMS</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#bulkTab"><i class="fas fa-layer-group"></i> Bulk SMS (8s delay)</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#scheduleTab"><i class="fas fa-calendar"></i> Schedule SMS</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#contactsTab"><i class="fas fa-address-book"></i> Contacts</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#historyTab"><i class="fas fa-history"></i> History</a></li>
        </ul>
        
        <div class="tab-content">
            <!-- Send SMS Tab -->
            <div class="tab-pane fade show active" id="sendTab">
                <div class="card">
                    <div class="card-header"><i class="fas fa-paper-plane"></i> Send Single SMS</div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-8">
                                <label>Phone Number</label>
                                <input type="text" id="number" class="form-control" placeholder="+216XXXXXXXX">
                            </div>
                            <div class="col-md-4">
                                <label>Quick Select</label>
                                <select id="quickContact" class="form-control" onchange="selectQuickContact()">
                                    <option value="">My contacts...</option>
                                </select>
                            </div>
                        </div>
                        <label class="mt-3">Message</label>
                        <textarea id="message" rows="4" class="form-control"></textarea>
                        <small id="charCount" class="text-muted">0/160</small>
                        <button class="btn btn-gradient mt-3" onclick="sendSMS()"><i class="fas fa-paper-plane"></i> Send</button>
                        <div id="result" class="mt-3"></div>
                    </div>
                </div>
            </div>
            
            <!-- Bulk SMS Tab -->
            <div class="tab-pane fade" id="bulkTab">
                <div class="card">
                    <div class="card-header"><i class="fas fa-layer-group"></i> Bulk SMS (8 seconds delay between each message)</div>
                    <div class="card-body">
                        <div class="alert alert-info">
                            <i class="fas fa-info-circle"></i> Each number will be sent with 8 second delay to avoid rate limiting.
                        </div>
                        
                        <label>Phone Numbers (one per line)</label>
                        <textarea id="bulkNumbers" rows="8" class="form-control" placeholder="+216XXXXXXXXX&#10;+216YYYYYYYYY&#10;+216ZZZZZZZZZ"></textarea>
                        <small id="numberCount" class="text-muted">0 numbers</small>
                        
                        <label class="mt-3">Message</label>
                        <textarea id="bulkMessage" rows="3" class="form-control" placeholder="Message to send to all numbers"></textarea>
                        
                        <div class="mt-2">
                            <label><i class="fas fa-hourglass-half"></i> Delay between messages: <span id="delayValue">8</span> seconds</label>
                            <input type="range" id="delaySlider" class="delay-slider" min="1" max="30" value="8" oninput="document.getElementById('delayValue').innerText=this.value">
                        </div>
                        
                        <button class="btn btn-gradient mt-3" onclick="startBulkSend()"><i class="fas fa-play"></i> Start Bulk Send</button>
                        <button class="btn btn-danger mt-3" onclick="stopBulkSend()" id="stopBtn" style="display:none;"><i class="fas fa-stop"></i> Stop</button>
                        
                        <div id="bulkProgress" class="mt-3" style="display:none;">
                            <div class="progress"><div id="bulkBar" class="progress-bar progress-bar-striped progress-bar-animated" style="width:0%">0%</div></div>
                            <div id="bulkStatus" class="mt-2"></div>
                        </div>
                        <div id="bulkResult" class="mt-3"></div>
                    </div>
                </div>
            </div>
            
            <!-- Schedule SMS Tab -->
            <div class="tab-pane fade" id="scheduleTab">
                <div class="card">
                    <div class="card-header"><i class="fas fa-calendar"></i> Schedule SMS</div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-8">
                                <label>Phone Number</label>
                                <input type="text" id="scheduleNumber" class="form-control" placeholder="+216XXXXXXXX">
                            </div>
                            <div class="col-md-4">
                                <label>Date & Time</label>
                                <input type="datetime-local" id="scheduleDateTime" class="form-control">
                            </div>
                        </div>
                        <label class="mt-3">Message</label>
                        <textarea id="scheduleMessage" rows="4" class="form-control"></textarea>
                        <button class="btn btn-gradient mt-3" onclick="scheduleSMS()"><i class="fas fa-calendar-plus"></i> Schedule</button>
                        
                        <hr>
                        <h5>📋 Pending Scheduled Messages</h5>
                        <div id="scheduledList" class="mt-2"></div>
                    </div>
                </div>
            </div>
            
            <!-- Contacts Tab -->
            <div class="tab-pane fade" id="contactsTab">
                <div class="card">
                    <div class="card-header">
                        <i class="fas fa-address-book"></i> My Contacts
                        <button class="btn btn-sm btn-success float-end" onclick="showAddContact()"><i class="fas fa-plus"></i> Add</button>
                    </div>
                    <div class="card-body">
                        <input type="text" id="searchContact" class="form-control mb-3" placeholder="Search...">
                        <div id="contactsList" class="list-group"></div>
                    </div>
                </div>
            </div>
            
            <!-- History Tab -->
            <div class="tab-pane fade" id="historyTab">
                <div class="card">
                    <div class="card-header"><i class="fas fa-history"></i> Message History</div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table" id="historyTable">
                                <thead><tr><th>Time</th><th>Number</th><th>Message</th><th>Status</th></tr></thead>
                                <tbody></tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Add Contact Modal -->
    <div class="modal fade" id="contactModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header"><h5>Add Contact</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
                <div class="modal-body">
                    <input type="text" id="contactName" class="form-control mb-2" placeholder="Name">
                    <input type="text" id="contactNumber" class="form-control mb-2" placeholder="Phone Number">
                    <input type="text" id="contactGroup" class="form-control" placeholder="Group">
                </div>
                <div class="modal-footer"><button class="btn btn-primary" onclick="addContact()">Save</button></div>
            </div>
        </div>
    </div>
    
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let bulkActive = false;
        let currentNumbers = [];
        
        document.getElementById('bulkNumbers').addEventListener('input', function() {
            let lines = this.value.split('\\n');
            currentNumbers = lines.filter(l => l.trim().match(/^\\+?[0-9]/));
            document.getElementById('numberCount').innerText = currentNumbers.length + ' numbers';
        });
        
        async function sendSMS() {
            let number = document.getElementById('number').value;
            let message = document.getElementById('message').value;
            if(!number || !message) { alert('Fill all fields'); return; }
            let res = await fetch('/api/send', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({number,message,key:'{{ api_key }}'})});
            let data = await res.json();
            document.getElementById('result').innerHTML = data.success ? '<div class="alert alert-success">✅ Sent!</div>' : '<div class="alert alert-danger">❌ Failed</div>';
            if(data.success) { document.getElementById('number').value = ''; document.getElementById('message').value = ''; loadStats(); loadHistory(); }
        }
        
        async function startBulkSend() {
            if(currentNumbers.length === 0) { alert('Add numbers first!'); return; }
            let message = document.getElementById('bulkMessage').value;
            if(!message) { alert('Enter a message!'); return; }
            let delay = parseInt(document.getElementById('delaySlider').value);
            
            if(!confirm(`Send to ${currentNumbers.length} numbers with ${delay}s delay? Total ~${Math.ceil(currentNumbers.length * delay / 60)} min`)) return;
            
            bulkActive = true;
            document.getElementById('bulkProgress').style.display = 'block';
            document.getElementById('stopBtn').style.display = 'inline-block';
            let sent = 0, failed = 0;
            
            for(let i = 0; i < currentNumbers.length && bulkActive; i++) {
                let percent = Math.round(((i+1)/currentNumbers.length)*100);
                document.getElementById('bulkBar').style.width = percent + '%';
                document.getElementById('bulkBar').innerText = percent + '%';
                document.getElementById('bulkStatus').innerHTML = `📤 Sending ${i+1}/${currentNumbers.length}... | ✅ Sent: ${sent} | ❌ Failed: ${failed}`;
                
                let res = await fetch('/api/send', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({number:currentNumbers[i], message, key:'{{ api_key }}'})});
                let data = await res.json();
                if(data.success) sent++; else failed++;
                
                if(i < currentNumbers.length - 1 && bulkActive) {
                    for(let s = delay; s > 0 && bulkActive; s--) {
                        document.getElementById('bulkStatus').innerHTML = `⏰ Waiting ${s}s... | ✅ Sent: ${sent} | ❌ Failed: ${failed}`;
                        await new Promise(r => setTimeout(r, 1000));
                    }
                }
            }
            document.getElementById('bulkProgress').style.display = 'none';
            document.getElementById('stopBtn').style.display = 'none';
            document.getElementById('bulkResult').innerHTML = `<div class="alert alert-success">✅ Complete! Sent: ${sent} | Failed: ${failed}</div>`;
            loadStats(); loadHistory(); bulkActive = false;
        }
        
        function stopBulkSend() { if(confirm('Stop?')) bulkActive = false; }
        
        async function scheduleSMS() {
            let number = document.getElementById('scheduleNumber').value;
            let message = document.getElementById('scheduleMessage').value;
            let scheduleTime = document.getElementById('scheduleDateTime').value;
            if(!number || !message || !scheduleTime) { alert('Fill all fields'); return; }
            let res = await fetch('/api/schedule', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({number, message, scheduleTime, key:'{{ api_key }}'})});
            let data = await res.json();
            if(data.success) { alert('✅ Scheduled!'); document.getElementById('scheduleNumber').value = ''; document.getElementById('scheduleMessage').value = ''; document.getElementById('scheduleDateTime').value = ''; loadScheduled(); loadStats(); }
            else alert('❌ Failed');
        }
        
        async function loadScheduled() {
            let res = await fetch('/api/scheduled');
            let data = await res.json();
            let html = '';
            for(let s of data.scheduled) {
                html += `<div class="alert alert-info"><strong>${s.number}</strong><br><small>${s.message.substring(0,50)}</small><br>📅 ${s.schedule_time}<br><span class="badge bg-warning">${s.status}</span></div>`;
            }
            document.getElementById('scheduledList').innerHTML = html || '<p>No scheduled messages</p>';
            document.getElementById('scheduledCount').innerText = data.scheduled.length;
        }
        
        async function loadStats() {
            let res = await fetch('/api/my-stats');
            let stats = await res.json();
            document.getElementById('totalSMS').innerText = stats.total;
            document.getElementById('successRate').innerText = stats.success_rate + '%';
            document.getElementById('myContacts').innerText = stats.contacts;
        }
        
        async function loadContacts() {
            let res = await fetch('/api/contacts');
            let contacts = await res.json();
            let html = '', selectHtml = '<option value="">Select contact...</option>';
            contacts.forEach(c => {
                html += `<div class="list-group-item"><div class="d-flex justify-content-between"><div><strong>${c.name}</strong><br><small>${c.number}</small></div><div><button class="btn btn-sm btn-primary" onclick="useNumber('${c.number}')">Send</button></div></div></div>`;
                selectHtml += `<option value="${c.number}">${c.name}</option>`;
            });
            document.getElementById('contactsList').innerHTML = html || '<p>No contacts</p>';
            document.getElementById('quickContact').innerHTML = selectHtml;
        }
        
        async function loadHistory() {
            let res = await fetch('/api/history');
            let data = await res.json();
            let html = '';
            data.history.forEach(h => { html += `<tr><td>${h.timestamp}</td><td>${h.number}</td><td>${h.message.substring(0,50)}</td><td>${h.status}</tr>`; });
            document.getElementById('historyTable tbody').innerHTML = html;
        }
        
        function useNumber(number) { document.getElementById('number').value = number; }
        function selectQuickContact() { document.getElementById('number').value = document.getElementById('quickContact').value; }
        function showAddContact() { new bootstrap.Modal(document.getElementById('contactModal')).show(); }
        
        async function addContact() {
            let contact = { name: document.getElementById('contactName').value, number: document.getElementById('contactNumber').value, group: document.getElementById('contactGroup').value };
            await fetch('/api/contacts', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(contact)});
            bootstrap.Modal.getInstance(document.getElementById('contactModal')).hide();
            loadContacts(); loadStats();
            document.getElementById('contactName').value = ''; document.getElementById('contactNumber').value = ''; document.getElementById('contactGroup').value = '';
        }
        
        document.getElementById('message').addEventListener('input', function() { document.getElementById('charCount').innerText = this.value.length + '/160'; });
        loadStats(); loadContacts(); loadHistory(); loadScheduled();
    </script>
</body>
</html>
'''

# Routes
@app.route('/')
def home():
    return HOME_PAGE

@app.route('/login/<username>', methods=['GET', 'POST'])
def login_user(username):
    conn = sqlite3.connect('sms_complete.db')
    c = conn.cursor()
    c.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    has_password = user and user[0] is not None
    
    if request.method == 'POST':
        password = request.form.get('password')
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if has_password:
            if user[0] == password_hash:
                session['username'] = username
                conn.close()
                return redirect(url_for('dashboard'))
            else:
                conn.close()
                return render_template_string(LOGIN_PAGE, username=username, has_password=True, error="Wrong password")
        else:
            c.execute("UPDATE users SET password_hash = ? WHERE username = ?", (password_hash, username))
            conn.commit()
            session['username'] = username
            conn.close()
            return redirect(url_for('dashboard'))
    conn.close()
    return render_template_string(LOGIN_PAGE, username=username, has_password=has_password, error=None)

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('home'))
    return render_template_string(DASHBOARD_PAGE, username=session['username'], api_key=API_KEY)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/api/send', methods=['POST'])
def api_send():
    if 'username' not in session:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json
    if data.get('key') != API_KEY:
        return jsonify({"error": "Invalid key"}), 403
    number, message = data.get('number'), data.get('message')
    if not number or not message:
        return jsonify({"error": "Missing"}), 400
    success, result = send_sms(number, message)
    conn = sqlite3.connect('sms_complete.db')
    c = conn.cursor()
    c.execute("INSERT INTO messages (username, number, message, status, timestamp) VALUES (?,?,?,?,?)",
              (session['username'], number, message, 'Sent' if success else 'Failed', datetime.datetime.now()))
    conn.commit()
    conn.close()
    return jsonify({"success": success, "message": result})

@app.route('/api/schedule', methods=['POST'])
def api_schedule():
    if 'username' not in session:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json
    if data.get('key') != API_KEY:
        return jsonify({"error": "Invalid key"}), 403
    schedule_time = datetime.datetime.fromisoformat(data.get('scheduleTime'))
    conn = sqlite3.connect('sms_complete.db')
    c = conn.cursor()
    c.execute("INSERT INTO scheduled (username, number, message, schedule_time, status) VALUES (?,?,?,?,?)",
              (session['username'], data['number'], data['message'], schedule_time, 'pending'))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/scheduled')
def api_scheduled():
    if 'username' not in session:
        return jsonify({"scheduled": []}), 401
    conn = sqlite3.connect('sms_complete.db')
    c = conn.cursor()
    c.execute("SELECT number, message, schedule_time, status FROM scheduled WHERE username = ? AND status = 'pending' ORDER BY schedule_time", (session['username'],))
    scheduled = [{"number": row[0], "message": row[1], "schedule_time": row[2], "status": row[3]} for row in c.fetchall()]
    conn.close()
    return jsonify({"scheduled": scheduled})

@app.route('/api/my-stats')
def my_stats():
    if 'username' not in session:
        return jsonify({}), 401
    conn = sqlite3.connect('sms_complete.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages WHERE username = ?", (session['username'],))
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM messages WHERE username = ? AND status = 'Sent'", (session['username'],))
    success = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM contacts WHERE username = ?", (session['username'],))
    contacts = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM scheduled WHERE username = ? AND status = 'pending'", (session['username'],))
    scheduled = c.fetchone()[0]
    success_rate = round((success / total * 100), 1) if total > 0 else 0
    conn.close()
    return jsonify({"total": total, "success_rate": success_rate, "contacts": contacts, "scheduled": scheduled})

@app.route('/api/contacts', methods=['GET', 'POST'])
def api_contacts():
    if 'username' not in session:
        return jsonify([]), 401
    conn = sqlite3.connect('sms_complete.db')
    c = conn.cursor()
    if request.method == 'POST':
        data = request.json
        c.execute("INSERT INTO contacts (username, name, number, group_name, created) VALUES (?,?,?,?,?)",
                  (session['username'], data['name'], data['number'], data.get('group'), datetime.datetime.now()))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    c.execute("SELECT name, number, group_name FROM contacts WHERE username = ? ORDER BY name", (session['username'],))
    contacts = [{"name": row[0], "number": row[1], "group_name": row[2]} for row in c.fetchall()]
    conn.close()
    return jsonify(contacts)

@app.route('/api/history')
def api_history():
    if 'username' not in session:
        return jsonify({"history": []}), 401
    conn = sqlite3.connect('sms_complete.db')
    c = conn.cursor()
    c.execute("SELECT timestamp, number, message, status FROM messages WHERE username = ? ORDER BY timestamp DESC LIMIT 50", (session['username'],))
    history = [{"timestamp": row[0], "number": row[1], "message": row[2], "status": row[3]} for row in c.fetchall()]
    conn.close()
    return jsonify({"history": history})

if __name__ == '__main__':
    print("="*60)
    print("🚀 SMS GATEWAY - COMPLETE WITH BULK & SCHEDULE")
    print("="*60)
    print(f"📱 Local URL: http://localhost:8080")
    print(f"🌐 Domain: https://atlasgrowthsms.website")
    print("="*60)
    print("✅ FEATURES:")
    print("   • Bulk SMS with 8-second delay")
    print("   • Schedule SMS for later")
    print("   • Contacts management")
    print("   • Message history")
    print("   • 6 user accounts (private passwords)")
    print("="*60)
    app.run(host='0.0.0.0', port=8080, debug=False)
