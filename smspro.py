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
    conn = sqlite3.connect('sms_ultimate.db')
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
                  username TEXT, numbers TEXT, message TEXT, schedule_time DATETIME, status TEXT, is_bulk INTEGER DEFAULT 0)''')
    
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
                time.sleep(1)
                return True, "Sent"
            else:
                if attempt < retry_count - 1:
                    time.sleep(2)
                    continue
                return False, "Failed"
        except:
            if attempt < retry_count - 1:
                time.sleep(2)
                continue
            return False, "Error"
    return False, "Unknown"

# Reliable bulk send function
def send_bulk_reliable(numbers, message, delay_seconds, username, callback=None):
    sent = 0
    failed = 0
    results = []
    
    for i, number in enumerate(numbers):
        try:
            success, status = send_sms(number.strip(), message)
            if success:
                sent += 1
                results.append({"number": number, "status": "Sent"})
            else:
                failed += 1
                results.append({"number": number, "status": "Failed"})
            
            # Log each message
            conn = sqlite3.connect('sms_ultimate.db')
            c = conn.cursor()
            c.execute("INSERT INTO messages (username, number, message, status, timestamp) VALUES (?,?,?,?,?)",
                      (username, number, message, 'Sent' if success else 'Failed', datetime.datetime.now()))
            conn.commit()
            conn.close()
            
            # Progress update via callback
            if callback:
                callback(i + 1, len(numbers), sent, failed)
            
            # Delay between messages (except last)
            if i < len(numbers) - 1:
                for remaining in range(delay_seconds, 0, -1):
                    if callback:
                        callback(i + 1, len(numbers), sent, failed, remaining)
                    time.sleep(1)
                    
        except Exception as e:
            failed += 1
            results.append({"number": number, "status": f"Error: {str(e)}"})
    
    return sent, failed, results

# Scheduler thread
def scheduler_worker():
    while True:
        try:
            now = datetime.datetime.now()
            conn = sqlite3.connect('sms_ultimate.db')
            c = conn.cursor()
            c.execute("SELECT id, numbers, message, username, is_bulk FROM scheduled WHERE schedule_time <= ? AND status = 'pending'", (now,))
            pending = c.fetchall()
            
            for schedule_id, numbers_json, message, username, is_bulk in pending:
                if is_bulk:
                    # Bulk schedule
                    import json
                    numbers = json.loads(numbers_json)
                    sent, failed, _ = send_bulk_reliable(numbers, message, 8, username)
                    c.execute("UPDATE scheduled SET status = ? WHERE id = ?", ('completed', schedule_id))
                else:
                    # Single schedule
                    success, _ = send_sms(numbers_json, message)
                    c.execute("UPDATE scheduled SET status = ? WHERE id = ?", ('sent' if success else 'failed', schedule_id))
                    c.execute("INSERT INTO messages (username, number, message, status, timestamp) VALUES (?,?,?,?,?)",
                              (username, numbers_json, message, 'Sent' if success else 'Failed', now))
                
                conn.commit()
            
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
            <h1>📱 SMS Gateway Pro</h1>
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
    <title>SMS Gateway Pro - {{ username }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        body { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 20px; font-family: 'Segoe UI', sans-serif; }
        .container { max-width: 1200px; margin: 0 auto; }
        .card { border-radius: 15px; box-shadow: 0 5px 15px rgba(0,0,0,0.2); margin-bottom: 20px; border: none; background: #0f3460; color: white; }
        .card-header { background: #e94560; border-bottom: none; font-weight: bold; border-radius: 15px 15px 0 0; color: white; }
        .btn-primary { background: #e94560; border: none; }
        .btn-primary:hover { background: #ff6b6b; transform: translateY(-2px); }
        .btn-success { background: #0f3460; border: none; }
        .btn-success:hover { background: #1a1a2e; }
        .btn-warning { background: #f5a623; border: none; color: white; }
        .btn-warning:hover { background: #ffc107; }
        .stat-card { background: #0f3460; border-radius: 15px; padding: 20px; text-align: center; margin-bottom: 20px; color: white; }
        .stat-value { font-size: 32px; font-weight: bold; color: #e94560; }
        .nav-tabs .nav-link { color: white; background: #0f3460; margin-right: 5px; border-radius: 10px 10px 0 0; }
        .nav-tabs .nav-link.active { background: #e94560; color: white; border: none; }
        .nav-tabs .nav-link:hover { background: #e94560; color: white; }
        .delay-slider { width: 100%; }
        .form-control, .form-select { background: #1a1a2e; border: 1px solid #e94560; color: white; }
        .form-control:focus, .form-select:focus { background: #1a1a2e; color: white; border-color: #ff6b6b; }
        .form-control::placeholder { color: #888; }
        .alert-info { background: #0f3460; color: #ff6b6b; border: 1px solid #e94560; }
        .alert-success { background: #0f3460; color: #00ff88; border: 1px solid #00ff88; }
        .alert-danger { background: #0f3460; color: #ff4444; border: 1px solid #ff4444; }
        .list-group-item { background: #1a1a2e; color: white; border: 1px solid #0f3460; }
        .modal-content { background: #0f3460; color: white; }
        .modal-header { border-bottom: 1px solid #e94560; }
        .modal-footer { border-top: 1px solid #e94560; }
        .btn-close { filter: invert(1); }
        table { color: white; }
        .badge { background: #e94560; }
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
                        <span class="badge"><i class="fas fa-user"></i> {{ username }}</span>
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
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#bulkTab"><i class="fas fa-layer-group"></i> Bulk SMS</a></li>
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
                                <select id="quickContact" class="form-select" onchange="selectQuickContact()">
                                    <option value="">My contacts...</option>
                                </select>
                            </div>
                        </div>
                        <label class="mt-3">Message</label>
                        <textarea id="message" rows="4" class="form-control"></textarea>
                        <small id="charCount" class="text-muted">0/160</small>
                        <button class="btn btn-primary mt-3" onclick="sendSMS()"><i class="fas fa-paper-plane"></i> Send</button>
                        <div id="result" class="mt-3"></div>
                    </div>
                </div>
            </div>
            
            <!-- Bulk SMS Tab - IMPROVED -->
            <div class="tab-pane fade" id="bulkTab">
                <div class="card">
                    <div class="card-header"><i class="fas fa-layer-group"></i> Bulk SMS (8 seconds delay)</div>
                    <div class="card-body">
                        <div class="alert alert-info">
                            <i class="fas fa-info-circle"></i> Each number sent with 8 second delay. Auto-retry on failure.
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
                        
                        <button class="btn btn-primary mt-3" onclick="startBulkSend()" id="startBulkBtn"><i class="fas fa-play"></i> Start Bulk Send</button>
                        <button class="btn btn-danger mt-3" onclick="stopBulkSend()" id="stopBulkBtn" style="display:none;"><i class="fas fa-stop"></i> Stop</button>
                        
                        <div id="bulkProgress" class="mt-3" style="display:none;">
                            <div class="progress mb-2"><div id="bulkBar" class="progress-bar progress-bar-striped progress-bar-animated bg-success" style="width:0%">0%</div></div>
                            <div id="bulkStatus" class="alert alert-info"></div>
                            <div id="bulkDetails" class="small text-muted"></div>
                        </div>
                        <div id="bulkResult" class="mt-3"></div>
                    </div>
                </div>
            </div>
            
            <!-- Schedule SMS Tab - WITH BULK SCHEDULE -->
            <div class="tab-pane fade" id="scheduleTab">
                <div class="card">
                    <div class="card-header"><i class="fas fa-calendar"></i> Schedule SMS</div>
                    <div class="card-body">
                        <ul class="nav nav-tabs mb-3" id="scheduleSubTabs">
                            <li class="nav-item"><a class="nav-link active" data-bs-toggle="tab" href="#singleSchedule"><i class="fas fa-envelope"></i> Single SMS</a></li>
                            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#bulkSchedule"><i class="fas fa-layer-group"></i> Bulk SMS</a></li>
                        </ul>
                        
                        <div class="tab-content">
                            <!-- Single Schedule -->
                            <div class="tab-pane fade show active" id="singleSchedule">
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
                                <textarea id="scheduleMessage" rows="3" class="form-control"></textarea>
                                <button class="btn btn-primary mt-3" onclick="scheduleSingleSMS()"><i class="fas fa-calendar-plus"></i> Schedule Single SMS</button>
                            </div>
                            
                            <!-- Bulk Schedule - NEW -->
                            <div class="tab-pane fade" id="bulkSchedule">
                                <div class="alert alert-info">
                                    <i class="fas fa-info-circle"></i> Schedule multiple numbers at once. Each message sent with 8 second delay.
                                </div>
                                
                                <label>Phone Numbers (one per line)</label>
                                <textarea id="bulkScheduleNumbers" rows="8" class="form-control" placeholder="+216XXXXXXXXX&#10;+216YYYYYYYYY&#10;+216ZZZZZZZZZ"></textarea>
                                <small id="bulkScheduleCount" class="text-muted">0 numbers</small>
                                
                                <label class="mt-3">Message</label>
                                <textarea id="bulkScheduleMessage" rows="3" class="form-control" placeholder="Message to send to all numbers"></textarea>
                                
                                <label class="mt-3">Schedule Date & Time</label>
                                <input type="datetime-local" id="bulkScheduleDateTime" class="form-control">
                                
                                <button class="btn btn-primary mt-3" onclick="scheduleBulkSMS()"><i class="fas fa-calendar-plus"></i> Schedule Bulk SMS</button>
                            </div>
                        </div>
                        
                        <hr class="mt-4">
                        <h5><i class="fas fa-clock"></i> Pending Scheduled Messages</h5>
                        <div id="scheduledList" class="mt-3"></div>
                    </div>
                </div>
            </div>
            
            <!-- Contacts Tab -->
            <div class="tab-pane fade" id="contactsTab">
                <div class="card">
                    <div class="card-header">
                        <i class="fas fa-address-book"></i> My Contacts
                        <button class="btn btn-success btn-sm float-end" onclick="showAddContact()"><i class="fas fa-plus"></i> Add Contact</button>
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
                            <table class="table table-dark table-hover" id="historyTable">
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
        let currentBulkNumbers = [];
        
        // Count numbers in bulk textarea
        document.getElementById('bulkNumbers')?.addEventListener('input', function() {
            let lines = this.value.split('\\n');
            currentBulkNumbers = lines.filter(l => l.trim().match(/^\\+?[0-9]/));
            document.getElementById('numberCount').innerText = currentBulkNumbers.length + ' numbers';
        });
        
        document.getElementById('bulkScheduleNumbers')?.addEventListener('input', function() {
            let lines = this.value.split('\\n');
            let numbers = lines.filter(l => l.trim().match(/^\\+?[0-9]/));
            document.getElementById('bulkScheduleCount').innerText = numbers.length + ' numbers';
        });
        
        // Send single SMS
        async function sendSMS() {
            let number = document.getElementById('number').value;
            let message = document.getElementById('message').value;
            if(!number || !message) { alert('Fill all fields'); return; }
            
            let resultDiv = document.getElementById('result');
            resultDiv.innerHTML = '<div class="alert alert-info">📤 Sending...</div>';
            
            let res = await fetch('/api/send', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({number, message, key: '{{ api_key }}'})
            });
            let data = await res.json();
            
            if(data.success) {
                resultDiv.innerHTML = '<div class="alert alert-success">✅ Sent!</div>';
                document.getElementById('number').value = '';
                document.getElementById('message').value = '';
                loadStats();
                loadHistory();
            } else {
                resultDiv.innerHTML = '<div class="alert alert-danger">❌ Failed</div>';
            }
        }
        
        // Start Bulk Send - IMPROVED AND RELIABLE
        async function startBulkSend() {
            if(currentBulkNumbers.length === 0) {
                alert('📋 Please add phone numbers first!');
                return;
            }
            
            let message = document.getElementById('bulkMessage').value;
            if(!message) {
                alert('✏️ Please enter a message!');
                return;
            }
            
            let delay = parseInt(document.getElementById('delaySlider').value);
            let totalTime = Math.ceil(currentBulkNumbers.length * delay / 60);
            
            let confirmMsg = `📊 Bulk SMS Details:\n\n`;
            confirmMsg += `📇 Numbers: ${currentBulkNumbers.length}\n`;
            confirmMsg += `⏱️ Delay: ${delay} seconds between messages\n`;
            confirmMsg += `⏰ Est. time: ~${totalTime} minutes\n\n`;
            confirmMsg += `🚀 Start sending?`;
            
            if(!confirm(confirmMsg)) return;
            
            bulkActive = true;
            document.getElementById('startBulkBtn').style.display = 'none';
            document.getElementById('stopBulkBtn').style.display = 'inline-block';
            document.getElementById('bulkProgress').style.display = 'block';
            document.getElementById('bulkResult').innerHTML = '';
            
            let sent = 0;
            let failed = 0;
            
            for(let i = 0; i < currentBulkNumbers.length && bulkActive; i++) {
                let number = currentBulkNumbers[i];
                let percent = Math.round(((i + 1) / currentBulkNumbers.length) * 100);
                
                document.getElementById('bulkBar').style.width = percent + '%';
                document.getElementById('bulkBar').innerText = percent + '%';
                document.getElementById('bulkStatus').innerHTML = `📤 Sending ${i+1}/${currentBulkNumbers.length} to ${number}`;
                document.getElementById('bulkDetails').innerHTML = `✅ Sent: ${sent} | ❌ Failed: ${failed}`;
                
                try {
                    let res = await fetch('/api/send', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({number, message, key: '{{ api_key }}'})
                    });
                    let data = await res.json();
                    
                    if(data.success) {
                        sent++;
                        document.getElementById('bulkStatus').innerHTML = `✅ ${i+1}/${currentBulkNumbers.length} - Sent to ${number}`;
                    } else {
                        failed++;
                        document.getElementById('bulkStatus').innerHTML = `❌ ${i+1}/${currentBulkNumbers.length} - Failed to ${number}`;
                    }
                    
                    document.getElementById('bulkDetails').innerHTML = `✅ Sent: ${sent} | ❌ Failed: ${failed}`;
                    
                } catch(error) {
                    failed++;
                    document.getElementById('bulkStatus').innerHTML = `⚠️ ${i+1}/${currentBulkNumbers.length} - Error to ${number}`;
                }
                
                // Delay between messages (except last)
                if(i < currentBulkNumbers.length - 1 && bulkActive) {
                    for(let s = delay; s > 0 && bulkActive; s--) {
                        document.getElementById('bulkDetails').innerHTML = `⏰ Waiting ${s}s... | ✅ Sent: ${sent} | ❌ Failed: ${failed}`;
                        await new Promise(r => setTimeout(r, 1000));
                    }
                }
            }
            
            document.getElementById('bulkProgress').style.display = 'none';
            document.getElementById('startBulkBtn').style.display = 'inline-block';
            document.getElementById('stopBulkBtn').style.display = 'none';
            
            let resultMsg = `✅ Bulk Send Complete!\n📊 Total: ${currentBulkNumbers.length}\n✅ Sent: ${sent}\n❌ Failed: ${failed}`;
            document.getElementById('bulkResult').innerHTML = `<div class="alert alert-success">${resultMsg.replace(/\\n/g, '<br>')}</div>`;
            
            loadStats();
            loadHistory();
            bulkActive = false;
            currentBulkNumbers = [];
            document.getElementById('bulkNumbers').value = '';
            document.getElementById('numberCount').innerText = '0 numbers';
        }
        
        function stopBulkSend() {
            if(confirm('🛑 Stop current bulk operation?')) {
                bulkActive = false;
                document.getElementById('bulkStatus').innerHTML = '⏹️ Stopped by user';
            }
        }
        
        // Schedule Single SMS
        async function scheduleSingleSMS() {
            let number = document.getElementById('scheduleNumber').value;
            let message = document.getElementById('scheduleMessage').value;
            let scheduleTime = document.getElementById('scheduleDateTime').value;
            
            if(!number || !message || !scheduleTime) {
                alert('Please fill all fields');
                return;
            }
            
            let res = await fetch('/api/schedule', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    number: number,
                    message: message,
                    scheduleTime: scheduleTime,
                    isBulk: false,
                    key: '{{ api_key }}'
                })
            });
            let data = await res.json();
            
            if(data.success) {
                alert('✅ SMS Scheduled successfully!');
                document.getElementById('scheduleNumber').value = '';
                document.getElementById('scheduleMessage').value = '';
                document.getElementById('scheduleDateTime').value = '';
                loadScheduled();
                loadStats();
            } else {
                alert('❌ Failed to schedule');
            }
        }
        
        // Schedule Bulk SMS - NEW
        async function scheduleBulkSMS() {
            let numbersText = document.getElementById('bulkScheduleNumbers').value;
            let numbers = numbersText.split('\\n').filter(l => l.trim().match(/^\\+?[0-9]/));
            let message = document.getElementById('bulkScheduleMessage').value;
            let scheduleTime = document.getElementById('bulkScheduleDateTime').value;
            
            if(numbers.length === 0) {
                alert('Please add phone numbers');
                return;
            }
            if(!message) {
                alert('Please enter a message');
                return;
            }
            if(!scheduleTime) {
                alert('Please select schedule date and time');
                return;
            }
            
            let totalTime = Math.ceil(numbers.length * 8 / 60);
            let confirmMsg = `📊 Schedule Bulk SMS:\n\n📇 Numbers: ${numbers.length}\n⏰ Time: ${scheduleTime}\n⏱️ Est. duration: ~${totalTime} minutes\n\n✅ Confirm schedule?`;
            
            if(!confirm(confirmMsg)) return;
            
            let res = await fetch('/api/schedule-bulk', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    numbers: numbers,
                    message: message,
                    scheduleTime: scheduleTime,
                    key: '{{ api_key }}'
                })
            });
            let data = await res.json();
            
            if(data.success) {
                alert(`✅ ${data.scheduled} SMS messages scheduled!`);
                document.getElementById('bulkScheduleNumbers').value = '';
                document.getElementById('bulkScheduleMessage').value = '';
                document.getElementById('bulkScheduleDateTime').value = '';
                loadScheduled();
                loadStats();
            } else {
                alert('❌ Failed to schedule: ' + (data.message || 'Unknown error'));
            }
        }
        
        // Load scheduled messages
        async function loadScheduled() {
            let res = await fetch('/api/scheduled');
            let data = await res.json();
            let html = '';
            for(let s of data.scheduled) {
                let isBulk = s.is_bulk ? '📦 Bulk' : '📧 Single';
                html += `<div class="alert alert-info">
                    <strong>${s.numbers_display}</strong><br>
                    <small>${s.message.substring(0,50)}</small><br>
                    📅 ${s.schedule_time}<br>
                    <span class="badge">${isBulk}</span>
                </div>`;
            }
            document.getElementById('scheduledList').innerHTML = html || '<p>No scheduled messages</p>';
            document.getElementById('scheduledCount').innerText = data.scheduled.length;
        }
        
        // Load stats
        async function loadStats() {
            let res = await fetch('/api/my-stats');
            let stats = await res.json();
            document.getElementById('totalSMS').innerText = stats.total;
            document.getElementById('successRate').innerText = stats.success_rate + '%';
            document.getElementById('myContacts').innerText = stats.contacts;
        }
        
        // Load contacts
        async function loadContacts() {
            let res = await fetch('/api/contacts');
            let contacts = await res.json();
            let html = '', selectHtml = '<option value="">Select contact...</option>';
            contacts.forEach(c => {
                html += `<div class="list-group-item">
                    <div class="d-flex justify-content-between">
                        <div><strong>${c.name}</strong><br><small>${c.number}</small></div>
                        <div><button class="btn btn-sm btn-primary" onclick="useNumber('${c.number}')">Send</button></div>
                    </div>
                </div>`;
                selectHtml += `<option value="${c.number}">${c.name}</option>`;
            });
            document.getElementById('contactsList').innerHTML = html || '<p>No contacts</p>';
            document.getElementById('quickContact').innerHTML = selectHtml;
        }
        
        // Load history
        async function loadHistory() {
            let res = await fetch('/api/history');
            let data = await res.json();
            let html = '';
            data.history.forEach(h => {
                html += `<tr>
                    <td>${h.timestamp}</td>
                    <td>${h.number}</td>
                    <td>${h.message.substring(0,50)}</td>
                    <td><span class="badge">${h.status}</span></td>
                </tr>`;
            });
            document.getElementById('historyTable tbody').innerHTML = html;
        }
        
        // Helper functions
        function useNumber(number) { document.getElementById('number').value = number; }
        function selectQuickContact() { document.getElementById('number').value = document.getElementById('quickContact').value; }
        function showAddContact() { new bootstrap.Modal(document.getElementById('contactModal')).show(); }
        
        async function addContact() {
            let contact = {
                name: document.getElementById('contactName').value,
                number: document.getElementById('contactNumber').value,
                group: document.getElementById('contactGroup').value
            };
            await fetch('/api/contacts', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(contact)});
            bootstrap.Modal.getInstance(document.getElementById('contactModal')).hide();
            loadContacts();
            loadStats();
            document.getElementById('contactName').value = '';
            document.getElementById('contactNumber').value = '';
            document.getElementById('contactGroup').value = '';
        }
        
        // Character counter
        document.getElementById('message')?.addEventListener('input', function() {
            document.getElementById('charCount').innerText = this.value.length + '/160';
        });
        
        // Initial loads
        loadStats();
        loadContacts();
        loadHistory();
        loadScheduled();
        
        // Auto refresh every 10 seconds
        setInterval(() => {
            loadStats();
            loadScheduled();
        }, 10000);
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
    conn = sqlite3.connect('sms_ultimate.db')
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
    conn = sqlite3.connect('sms_ultimate.db')
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
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    c.execute("INSERT INTO scheduled (username, numbers, message, schedule_time, status, is_bulk) VALUES (?,?,?,?,?,?)",
              (session['username'], data['number'], data['message'], schedule_time, 'pending', 0))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/schedule-bulk', methods=['POST'])
def api_schedule_bulk():
    if 'username' not in session:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json
    if data.get('key') != API_KEY:
        return jsonify({"error": "Invalid key"}), 403
    
    numbers = data.get('numbers', [])
    message = data.get('message')
    schedule_time = datetime.datetime.fromisoformat(data.get('scheduleTime'))
    
    import json
    numbers_json = json.dumps(numbers)
    
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    c.execute("INSERT INTO scheduled (username, numbers, message, schedule_time, status, is_bulk) VALUES (?,?,?,?,?,?)",
              (session['username'], numbers_json, message, schedule_time, 'pending', 1))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "scheduled": len(numbers)})

@app.route('/api/scheduled')
def api_scheduled():
    if 'username' not in session:
        return jsonify({"scheduled": []}), 401
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    c.execute("SELECT numbers, message, schedule_time, status, is_bulk FROM scheduled WHERE username = ? AND status = 'pending' ORDER BY schedule_time", (session['username'],))
    scheduled = []
    for row in c.fetchall():
        numbers, message, schedule_time, status, is_bulk = row
        if is_bulk:
            import json
            nums = json.loads(numbers)
            display = f"Bulk ({len(nums)} numbers)"
        else:
            display = numbers
        scheduled.append({
            "numbers_display": display,
            "message": message,
            "schedule_time": schedule_time,
            "status": status,
            "is_bulk": is_bulk
        })
    conn.close()
    return jsonify({"scheduled": scheduled})

@app.route('/api/my-stats')
def my_stats():
    if 'username' not in session:
        return jsonify({}), 401
    conn = sqlite3.connect('sms_ultimate.db')
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
    conn = sqlite3.connect('sms_ultimate.db')
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
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    c.execute("SELECT timestamp, number, message, status FROM messages WHERE username = ? ORDER BY timestamp DESC LIMIT 100", (session['username'],))
    history = [{"timestamp": row[0], "number": row[1], "message": row[2], "status": row[3]} for row in c.fetchall()]
    conn.close()
    return jsonify({"history": history})

if __name__ == '__main__':
    print("="*60)
    print("🚀 SMS ULTIMATE COMPLETE - ALL FEATURES")
    print("="*60)
    print(f"📱 Local URL: http://localhost:8080")
    print(f"🌐 Domain: https://atlasgrowthsms.website")
    print("="*60)
    print("✅ ALL FEATURES:")
    print("   • Send Single SMS")
    print("   • Bulk SMS (8s delay, stop button, progress)")
    print("   • Schedule Single SMS")
    print("   • Schedule BULK SMS (NEW!)")
    print("   • Contacts Management")
    print("   • Message History")
    print("   • 6 User Accounts (Private passwords)")
    print("="*60)
    app.run(host='0.0.0.0', port=8080, debug=False)
