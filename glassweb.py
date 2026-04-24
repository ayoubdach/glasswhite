from flask import Flask, request, jsonify, render_template_string, session
from flask_cors import CORS
import subprocess, sqlite3, datetime, secrets, time, threading
from functools import wraps

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
CORS(app)

# Configuration
API_KEY = "GlasswhiteUltimate2026"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
SMS_DELAY_SECONDS = 8  # Default delay between messages

# Database setup
def init_db():
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  number TEXT, message TEXT, status TEXT, 
                  timestamp DATETIME, sender_ip TEXT, 
                  delay_used INTEGER DEFAULT 8)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS contacts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT, number TEXT, group_name TEXT, 
                  created DATETIME)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS templates
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT, content TEXT, created DATETIME)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS groups
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT, created DATETIME)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS blacklist
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  number TEXT UNIQUE, reason TEXT, created DATETIME)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS bulk_jobs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  total_numbers INTEGER, sent_count INTEGER, 
                  failed_count INTEGER, status TEXT, 
                  created DATETIME, progress INTEGER DEFAULT 0)''')
    
    conn.commit()
    conn.close()

init_db()

# Send SMS function with retry
def send_sms(number, message):
    try:
        subprocess.run(['termux-sms-send', '-n', number, message], timeout=15)
        return True, "Sent"
    except Exception as e:
        return False, str(e)

# Bulk send with delay
def send_bulk_with_delay(numbers, message, delay_seconds, job_id=None, progress_callback=None):
    sent = 0
    failed = 0
    
    for i, number in enumerate(numbers):
        success, result = send_sms(number, message)
        
        if success:
            sent += 1
            # Log individual message
            conn = sqlite3.connect('sms_ultimate.db')
            c = conn.cursor()
            c.execute("INSERT INTO messages (number, message, status, timestamp, delay_used) VALUES (?,?,?,?,?)",
                      (number, message, 'Sent', datetime.datetime.now(), delay_seconds))
            conn.commit()
            conn.close()
        else:
            failed += 1
        
        # Update progress
        progress = int(((i + 1) / len(numbers)) * 100)
        
        if job_id:
            conn = sqlite3.connect('sms_ultimate.db')
            c = conn.cursor()
            c.execute("UPDATE bulk_jobs SET sent_count=?, failed_count=?, progress=? WHERE id=?", 
                      (sent, failed, progress, job_id))
            conn.commit()
            conn.close()
        
        # Wait between messages (except after last)
        if i < len(numbers) - 1:
            time.sleep(delay_seconds)
    
    if job_id:
        conn = sqlite3.connect('sms_ultimate.db')
        c = conn.cursor()
        c.execute("UPDATE bulk_jobs SET status=?, sent_count=?, failed_count=?, progress=100 WHERE id=?", 
                  ('Completed', sent, failed, job_id))
        conn.commit()
        conn.close()
    
    return sent, failed

# HTML Dashboard with Delay Controls
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SMS Ultimate Pro - With Delay Control</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); font-family: 'Segoe UI', sans-serif; padding: 20px; }
        .container-fluid { max-width: 1400px; margin: 0 auto; }
        .card { border-radius: 15px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); margin-bottom: 20px; border: none; }
        .card-header { background: white; border-bottom: 2px solid #f0f0f0; font-weight: bold; border-radius: 15px 15px 0 0; }
        .btn-gradient { background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; }
        .btn-gradient:hover { transform: translateY(-2px); color: white; }
        .stat-card { background: white; border-radius: 15px; padding: 20px; text-align: center; margin-bottom: 20px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
        .stat-value { font-size: 32px; font-weight: bold; color: #667eea; }
        .progress-bar-gradient { background: linear-gradient(135deg, #667eea, #764ba2); }
        .delay-slider { width: 100%; margin: 10px 0; }
        .delay-value { font-size: 24px; font-weight: bold; color: #667eea; }
        .nav-tabs .nav-link.active { background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; }
        .number-list-item { cursor: pointer; padding: 10px; border-bottom: 1px solid #eee; transition: 0.2s; }
        .number-list-item:hover { background: #f0f0f0; transform: scale(1.02); }
        .badge-delay { background: #ff9800; color: white; }
    </style>
</head>
<body>
    <div class="container-fluid">
        <!-- Header -->
        <div class="card">
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <h2><i class="fas fa-sms"></i> SMS Ultimate Pro</h2>
                        <p class="text-muted">Advanced SMS Gateway with Delay Control</p>
                    </div>
                    <div class="col-md-6 text-end">
                        <button class="btn btn-danger" onclick="logout()"><i class="fas fa-sign-out-alt"></i> Logout</button>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Stats Row -->
        <div class="row">
            <div class="col-md-3"><div class="stat-card"><i class="fas fa-envelope fa-2x"></i><div class="stat-value" id="totalSMS">0</div><div>Total SMS</div></div></div>
            <div class="col-md-3"><div class="stat-card"><i class="fas fa-check-circle fa-2x"></i><div class="stat-value" id="successRate">0%</div><div>Success Rate</div></div></div>
            <div class="col-md-3"><div class="stat-card"><i class="fas fa-users fa-2x"></i><div class="stat-value" id="totalContacts">0</div><div>Contacts</div></div></div>
            <div class="col-md-3"><div class="stat-card"><i class="fas fa-clock fa-2x"></i><div class="stat-value" id="todaySMS">0</div><div>Today's SMS</div></div></div>
        </div>
        
        <!-- Tabs -->
        <ul class="nav nav-tabs mb-3" id="myTab" role="tablist">
            <li class="nav-item"><a class="nav-link active" data-bs-toggle="tab" href="#dashboard"><i class="fas fa-chart-line"></i> Dashboard</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#send"><i class="fas fa-paper-plane"></i> Send SMS</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#bulk"><i class="fas fa-layer-group"></i> Bulk SMS</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#contacts"><i class="fas fa-address-book"></i> Contacts</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#groups"><i class="fas fa-users"></i> Groups</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#templates"><i class="fas fa-file-alt"></i> Templates</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#history"><i class="fas fa-history"></i> History</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#settings"><i class="fas fa-cog"></i> Settings</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#api"><i class="fas fa-code"></i> API</a></li>
        </ul>
        
        <div class="tab-content">
            <!-- Dashboard Tab -->
            <div class="tab-pane fade show active" id="dashboard">
                <div class="card">
                    <div class="card-body">
                        <canvas id="smsChart" height="80"></canvas>
                    </div>
                </div>
                <div class="card">
                    <div class="card-header"><i class="fas fa-history"></i> Recent Messages</div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table" id="recentTable">
                                <thead><tr><th>Time</th><th>Number</th><th>Message</th><th>Status</th><th>Delay</th></tr></thead>
                                <tbody></tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Send SMS Tab -->
            <div class="tab-pane fade" id="send">
                <div class="card">
                    <div class="card-header"><i class="fas fa-paper-plane"></i> Send Single SMS</div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-8">
                                <label>Phone Number</label>
                                <div class="input-group">
                                    <input type="text" id="singleNumber" class="form-control" placeholder="+216XXXXXXXX">
                                    <button class="btn btn-secondary" onclick="showContactList()"><i class="fas fa-list"></i> From Contacts</button>
                                </div>
                            </div>
                            <div class="col-md-4">
                                <label>Quick Select</label>
                                <select id="quickNumber" class="form-control" onchange="selectQuickNumber()">
                                    <option value="">Select from list...</option>
                                </select>
                            </div>
                        </div>
                        
                        <label class="mt-3">Message</label>
                        <textarea id="singleMessage" rows="4" class="form-control" placeholder="Type your message here..."></textarea>
                        <small id="charCount" class="text-muted">0 / 160 characters</small>
                        
                        <div class="row mt-3">
                            <div class="col-md-6">
                                <label><i class="fas fa-hourglass-half"></i> Delay Between Messages (seconds)</label>
                                <input type="range" id="delaySlider" class="delay-slider" min="1" max="30" value="8" oninput="updateDelayValue()">
                                <div><span id="delayValue" class="delay-value">8</span> seconds</div>
                            </div>
                        </div>
                        
                        <button class="btn btn-gradient mt-3" onclick="sendSMS()"><i class="fas fa-paper-plane"></i> Send Now</button>
                        <button class="btn btn-secondary mt-3" onclick="saveAsTemplate()"><i class="fas fa-save"></i> Save as Template</button>
                        <div id="sendResult" class="mt-3"></div>
                    </div>
                </div>
            </div>
            
            <!-- Bulk SMS Tab -->
            <div class="tab-pane fade" id="bulk">
                <div class="card">
                    <div class="card-header"><i class="fas fa-layer-group"></i> Bulk SMS with Delay</div>
                    <div class="card-body">
                        <div class="alert alert-info">
                            <i class="fas fa-info-circle"></i> Each message will be sent with <span id="bulkDelayPreview">8</span> second delay to avoid rate limiting
                        </div>
                        
                        <ul class="nav nav-tabs" id="bulkTabs">
                            <li class="nav-item"><a class="nav-link active" data-bs-toggle="tab" href="#pasteTab">Paste Numbers</a></li>
                            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#fileTab">Import File</a></li>
                            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#groupTab">Select Group</a></li>
                        </ul>
                        
                        <div class="tab-content mt-3">
                            <div class="tab-pane active" id="pasteTab">
                                <label>Paste Numbers (one per line)</label>
                                <textarea id="bulkNumbers" rows="6" class="form-control" placeholder="+216XXXXXXXXX&#10;+216YYYYYYYYY&#10;+216ZZZZZZZZZ"></textarea>
                                <small class="text-muted">Total: <span id="pasteCount">0</span> numbers</small>
                            </div>
                            
                            <div class="tab-pane" id="fileTab">
                                <label>Import CSV File</label>
                                <input type="file" id="csvFile" class="form-control" accept=".csv,.txt" onchange="previewCSV()">
                                <div id="csvPreview" class="mt-2"></div>
                            </div>
                            
                            <div class="tab-pane" id="groupTab">
                                <label>Select Group</label>
                                <select id="bulkGroup" class="form-control" onchange="loadGroupNumbers()">
                                    <option value="">Choose group...</option>
                                </select>
                                <div id="groupNumbersPreview" class="mt-2"></div>
                            </div>
                        </div>
                        
                        <label class="mt-3">Message</label>
                        <textarea id="bulkMessage" rows="3" class="form-control" placeholder="Message to send to all numbers"></textarea>
                        
                        <div class="row mt-3">
                            <div class="col-md-6">
                                <label><i class="fas fa-hourglass-half"></i> Delay Between Messages</label>
                                <input type="range" id="bulkDelaySlider" class="delay-slider" min="1" max="30" value="8" oninput="updateBulkDelayValue()">
                                <div><span id="bulkDelayValue" class="delay-value">8</span> seconds</div>
                                <small class="text-muted">For 100 messages: ~{(100*8)/60} minutes</small>
                            </div>
                            <div class="col-md-6">
                                <label><i class="fas fa-chart-line"></i> Estimated Time</label>
                                <div id="estimatedTime" class="alert alert-info">0 seconds</div>
                            </div>
                        </div>
                        
                        <button class="btn btn-gradient mt-3" onclick="startBulkSend()"><i class="fas fa-rocket"></i> Start Bulk Send</button>
                        <button class="btn btn-warning mt-3" onclick="stopBulkSend()" id="stopBtn" style="display:none;"><i class="fas fa-stop"></i> Stop</button>
                        
                        <div id="bulkProgress" class="mt-3" style="display:none;">
                            <div class="progress">
                                <div id="bulkBar" class="progress-bar progress-bar-gradient" role="progressbar" style="width:0%"></div>
                            </div>
                            <div id="bulkStatus" class="mt-2"></div>
                            <div id="bulkDetails" class="mt-2 small text-muted"></div>
                        </div>
                        
                        <div id="bulkResult" class="mt-3"></div>
                    </div>
                </div>
            </div>
            
            <!-- Contacts Tab -->
            <div class="tab-pane fade" id="contacts">
                <div class="card">
                    <div class="card-header">
                        <i class="fas fa-address-book"></i> Contacts
                        <button class="btn btn-sm btn-success float-end" onclick="showAddContact()"><i class="fas fa-plus"></i> Add Contact</button>
                    </div>
                    <div class="card-body">
                        <input type="text" id="searchContact" class="form-control mb-3" placeholder="Search contacts..." onkeyup="filterContacts()">
                        <div id="contactsList" class="list-group"></div>
                    </div>
                </div>
            </div>
            
            <!-- Groups Tab -->
            <div class="tab-pane fade" id="groups">
                <div class="card">
                    <div class="card-header">
                        <i class="fas fa-users"></i> Groups
                        <button class="btn btn-sm btn-success float-end" onclick="showAddGroup()"><i class="fas fa-plus"></i> Create Group</button>
                    </div>
                    <div class="card-body"><div id="groupsList"></div></div>
                </div>
            </div>
            
            <!-- Templates Tab -->
            <div class="tab-pane fade" id="templates">
                <div class="card">
                    <div class="card-header">
                        <i class="fas fa-file-alt"></i> Templates
                        <button class="btn btn-sm btn-success float-end" onclick="showAddTemplate()"><i class="fas fa-plus"></i> Add Template</button>
                    </div>
                    <div class="card-body"><div id="templatesList"></div></div>
                </div>
            </div>
            
            <!-- History Tab -->
            <div class="tab-pane fade" id="history">
                <div class="card">
                    <div class="card-header"><i class="fas fa-history"></i> Message History</div>
                    <div class="card-body">
                        <div class="row mb-3">
                            <div class="col-md-4">
                                <input type="text" id="searchHistory" class="form-control" placeholder="Search by number..." onkeyup="searchHistory()">
                            </div>
                            <div class="col-md-3">
                                <select id="filterStatus" class="form-control" onchange="filterHistory()">
                                    <option value="">All Status</option>
                                    <option value="Sent">Success</option>
                                    <option value="Failed">Failed</option>
                                </select>
                            </div>
                            <div class="col-md-3">
                                <button class="btn btn-info" onclick="exportHistory()"><i class="fas fa-download"></i> Export CSV</button>
                            </div>
                        </div>
                        <div class="table-responsive">
                            <table class="table" id="historyTable">
                                <thead><tr><th>Time</th><th>Number</th><th>Message</th><th>Status</th><th>Delay</th></tr></thead>
                                <tbody></tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Settings Tab -->
            <div class="tab-pane fade" id="settings">
                <div class="card">
                    <div class="card-header"><i class="fas fa-cog"></i> Global Settings</div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-6">
                                <label><i class="fas fa-hourglass-half"></i> Default Delay (seconds)</label>
                                <input type="number" id="globalDelay" class="form-control" value="8" min="1" max="60">
                                <button class="btn btn-primary mt-2" onclick="updateGlobalDelay()">Save Settings</button>
                            </div>
                            <div class="col-md-6">
                                <label><i class="fas fa-database"></i> Database Stats</label>
                                <div id="dbStats"></div>
                                <button class="btn btn-danger mt-2" onclick="clearHistory()">Clear All History</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- API Tab -->
            <div class="tab-pane fade" id="api">
                <div class="card">
                    <div class="card-header"><i class="fas fa-code"></i> API Documentation</div>
                    <div class="card-body">
                        <h5>Send Single SMS</h5>
                        <pre class="bg-light p-2 rounded">GET /api/send?key={{ api_key }}&to=NUMBER&text=MESSAGE&delay=8</pre>
                        
                        <h5>Send Bulk SMS</h5>
                        <pre class="bg-light p-2 rounded">POST /api/bulk
{
    "key": "{{ api_key }}",
    "numbers": ["+216XXX", "+216YYY"],
    "message": "Hello",
    "delay": 8
}</pre>
                        
                        <h5>Your API Key:</h5>
                        <code class="bg-light p-2 d-block">{{ api_key }}</code>
                        
                        <button class="btn btn-secondary mt-2" onclick="copyAPIKey()"><i class="fas fa-copy"></i> Copy API Key</button>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Modals -->
    <div class="modal fade" id="contactModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
        <div class="modal-header"><h5>Add Contact</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
        <div class="modal-body">
            <input type="text" id="contactName" class="form-control mb-2" placeholder="Name">
            <input type="text" id="contactNumber" class="form-control mb-2" placeholder="Phone Number">
            <input type="text" id="contactGroup" class="form-control" placeholder="Group">
        </div>
        <div class="modal-footer"><button class="btn btn-primary" onclick="addContact()">Save</button></div>
    </div></div></div>
    
    <div class="modal fade" id="groupModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
        <div class="modal-header"><h5>Create Group</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
        <div class="modal-body"><input type="text" id="groupName" class="form-control" placeholder="Group Name"></div>
        <div class="modal-footer"><button class="btn btn-primary" onclick="createGroup()">Create</button></div>
    </div></div></div>
    
    <div class="modal fade" id="templateModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
        <div class="modal-header"><h5>Add Template</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
        <div class="modal-body">
            <input type="text" id="templateName" class="form-control mb-2" placeholder="Template Name">
            <textarea id="templateContent" rows="3" class="form-control" placeholder="Template Content"></textarea>
        </div>
        <div class="modal-footer"><button class="btn btn-primary" onclick="addTemplate()">Save</button></div>
    </div></div></div>
    
    <div class="modal fade" id="contactListModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
        <div class="modal-header"><h5>Select Contact</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
        <div class="modal-body"><div id="contactSelector"></div></div>
    </div></div></div>
    
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let chart = null;
        let currentBulkNumbers = [];
        let bulkJobActive = false;
        
        function updateDelayValue() {
            let val = document.getElementById('delaySlider').value;
            document.getElementById('delayValue').innerText = val;
        }
        
        function updateBulkDelayValue() {
            let val = document.getElementById('bulkDelaySlider').value;
            document.getElementById('bulkDelayValue').innerText = val;
            document.getElementById('bulkDelayPreview').innerText = val;
            updateEstimatedTime();
        }
        
        function updateEstimatedTime() {
            let numbers = currentBulkNumbers.length;
            let delay = parseInt(document.getElementById('bulkDelaySlider').value);
            let totalSeconds = numbers * delay;
            let minutes = Math.floor(totalSeconds / 60);
            let seconds = totalSeconds % 60;
            document.getElementById('estimatedTime').innerHTML = `${numbers} messages × ${delay}s = ~${minutes} min ${seconds} sec`;
        }
        
        async function sendSMS() {
            let number = document.getElementById('singleNumber').value;
            let message = document.getElementById('singleMessage').value;
            let delay = document.getElementById('delaySlider').value;
            
            if(!number || !message) {
                alert('Fill all fields');
                return;
            }
            
            let res = await fetch('/api/send', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({number, message, delay, key: '{{ api_key }}'})
            });
            let data = await res.json();
            
            document.getElementById('sendResult').innerHTML = data.success ? 
                '<div class="alert alert-success">✅ Sent successfully!</div>' : 
                '<div class="alert alert-danger">❌ Failed: ' + data.message + '</div>';
            
            if(data.success) {
                document.getElementById('singleNumber').value = '';
                document.getElementById('singleMessage').value = '';
                loadDashboard();
                loadHistory();
            }
        }
        
        async function startBulkSend() {
            let numbers = [...currentBulkNumbers];
            let message = document.getElementById('bulkMessage').value;
            let delay = parseInt(document.getElementById('bulkDelaySlider').value);
            
            if(numbers.length === 0) {
                alert('No numbers to send. Add numbers first!');
                return;
            }
            if(!message) {
                alert('Enter a message!');
                return;
            }
            
            if(!confirm(`Send to ${numbers.length} numbers with ${delay}s delay between each?\nEstimated time: ${(numbers.length*delay/60).toFixed(1)} minutes`)) {
                return;
            }
            
            bulkJobActive = true;
            document.getElementById('bulkProgress').style.display = 'block';
            document.getElementById('stopBtn').style.display = 'inline-block';
            document.getElementById('bulkBar').style.width = '0%';
            
            let sent = 0;
            let failed = 0;
            
            for(let i = 0; i < numbers.length && bulkJobActive; i++) {
                let percent = ((i + 1) / numbers.length) * 100;
                document.getElementById('bulkBar').style.width = percent + '%';
                document.getElementById('bulkStatus').innerHTML = `Sending ${i+1}/${numbers.length}...`;
                document.getElementById('bulkDetails').innerHTML = `✅ Sent: ${sent} | ❌ Failed: ${failed} | ⏱️ Next message in ${delay}s`;
                
                let res = await fetch('/api/send', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({number: numbers[i], message, delay: 0, key: '{{ api_key }}'})
                });
                let data = await res.json();
                
                if(data.success) sent++;
                else failed++;
                
                if(i < numbers.length - 1 && bulkJobActive) {
                    for(let s = delay; s > 0 && bulkJobActive; s--) {
                        document.getElementById('bulkDetails').innerHTML = `✅ Sent: ${sent} | ❌ Failed: ${failed} | ⏰ Waiting ${s}s...`;
                        await new Promise(r => setTimeout(r, 1000));
                    }
                }
            }
            
            document.getElementById('bulkProgress').style.display = 'none';
            document.getElementById('stopBtn').style.display = 'none';
            
            if(bulkJobActive) {
                document.getElementById('bulkResult').innerHTML = `
                    <div class="alert alert-success">
                        <h5>✅ Bulk Send Complete!</h5>
                        <p>Total: ${numbers.length} | Sent: ${sent} | Failed: ${failed}</p>
                    </div>
                `;
                loadDashboard();
                loadHistory();
            } else {
                document.getElementById('bulkResult').innerHTML = `<div class="alert alert-warning">⏹️ Stopped by user. Sent: ${sent} | Failed: ${failed}</div>`;
            }
            
            bulkJobActive = false;
        }
        
        function stopBulkSend() {
            if(confirm('Stop current bulk operation?')) {
                bulkJobActive = false;
                document.getElementById('bulkStatus').innerHTML = '⏹️ Stopping...';
            }
        }
        
        function previewCSV() {
            let file = document.getElementById('csvFile').files[0];
            if(!file) return;
            
            let reader = new FileReader();
            reader.onload = function(e) {
                let text = e.target.result;
                let lines = text.split('\\n');
                let numbers = lines.filter(l => l.trim().match(/^\\+?[0-9]/));
                currentBulkNumbers = numbers;
                document.getElementById('csvPreview').innerHTML = `<div class="alert alert-info">📊 Loaded ${numbers.length} numbers</div>`;
                updateEstimatedTime();
            };
            reader.readAsText(file);
        }
        
        async function loadGroupNumbers() {
            let groupId = document.getElementById('bulkGroup').value;
            if(!groupId) return;
            
            let res = await fetch(`/api/group-contacts/${groupId}`);
            let contacts = await res.json();
            currentBulkNumbers = contacts.map(c => c.number);
            document.getElementById('groupNumbersPreview').innerHTML = `<div class="alert alert-info">👥 Group has ${contacts.length} members</div>`;
            updateEstimatedTime();
        }
        
        document.getElementById('bulkNumbers').addEventListener('input', function() {
            let lines = this.value.split('\\n');
            let numbers = lines.filter(l => l.trim());
            currentBulkNumbers = numbers;
            document.getElementById('pasteCount').innerText = numbers.length;
            updateEstimatedTime();
        });
        
        async function loadDashboard() {
            let stats = await fetch('/api/stats').then(r=>r.json());
            document.getElementById('totalSMS').innerText = stats.total;
            document.getElementById('successRate').innerText = stats.success_rate+'%';
            document.getElementById('totalContacts').innerText = stats.contacts;
            document.getElementById('todaySMS').innerText = stats.today;
            
            let chartData = await fetch('/api/chart-data').then(r=>r.json());
            if(chart) chart.destroy();
            let ctx = document.getElementById('smsChart').getContext('2d');
            chart = new Chart(ctx, {
                type: 'line',
                data: { labels: chartData.labels, datasets: [{ label: 'SMS Sent', data: chartData.values, borderColor: '#667eea', fill: false, tension: 0.4 }] }
            });
            
            let history = await fetch('/api/history?limit=10').then(r=>r.json());
            let html = '';
            history.history.slice(0,10).forEach(h => {
                html += `<tr><td>${h.timestamp}</td><td>${h.number}</td><td>${h.message.substring(0,40)}</td><td><span class="badge bg-${h.status=='Sent'?'success':'danger'}">${h.status}</span></td><td><span class="badge bg-info">${h.delay_used || 8}s</span></td></tr>`;
            });
            document.querySelector('#recentTable tbody').innerHTML = html;
        }
        
        async function loadContacts() {
            let contacts = await fetch('/api/contacts').then(r=>r.json());
            let html = '';
            contacts.forEach(c => {
                html += `<div class="list-group-item"><div class="d-flex justify-content-between align-items-center"><div><strong>${c.name}</strong><br><small>${c.number}</small><br><small class="text-muted">${c.group_name || 'No group'}</small></div><div><button class="btn btn-sm btn-primary" onclick="selectContact('${c.number}')"><i class="fas fa-paper-plane"></i></button><button class="btn btn-sm btn-danger" onclick="deleteContact(${c.id})"><i class="fas fa-trash"></i></button></div></div></div>`;
            });
            document.getElementById('contactsList').innerHTML = html || '<div class="alert alert-info">No contacts yet. Add some!</div>';
        }
        
        async function loadGroups() {
            let groups = await fetch('/api/groups').then(r=>r.json());
            let groupSelect = '<option value="">Choose group...</option>';
            let html = '';
            
            for(let g of groups) {
                let members = await fetch(`/api/group-contacts/${g.id}`).then(r=>r.json());
                groupSelect += `<option value="${g.id}">${g.name} (${members.length})</option>`;
                html += `<div class="card mb-2"><div class="card-body"><strong><i class="fas fa-users"></i> ${g.name}</strong> <span class="badge bg-primary">${members.length} members</span><br><button class="btn btn-sm btn-primary mt-2" onclick="sendToGroup(${g.id})"><i class="fas fa-paper-plane"></i> Send to Group</button><button class="btn btn-sm btn-danger mt-2" onclick="deleteGroup(${g.id})">Delete</button></div></div>`;
            }
            document.getElementById('groupsList').innerHTML = html || '<p>No groups yet</p>';
            document.getElementById('bulkGroup').innerHTML = groupSelect;
        }
        
        async function loadTemplates() {
            let templates = await fetch('/api/templates').then(r=>r.json());
            let html = '<div class="row">';
            templates.forEach(t => {
                html += `<div class="col-md-4 mb-2"><div class="card"><div class="card-body"><strong>${t.name}</strong><p class="small text-muted mt-2">${t.content.substring(0,80)}</p><button class="btn btn-sm btn-primary" onclick="useTemplate('${t.content.replace(/'/g, "\\'")}')">Use</button><button class="btn btn-sm btn-danger" onclick="deleteTemplate(${t.id})">Delete</button></div></div></div>`;
            });
            html += '</div>';
            document.getElementById('templatesList').innerHTML = html || '<p>No templates yet</p>';
        }
        
        async function loadHistory() {
            let history = await fetch('/api/history').then(r=>r.json());
            let html = '';
            history.history.forEach(h => {
                html += `<tr>
                    <td>${h.timestamp}</td>
                    <td>${h.number}</td>
                    <td>${h.message.substring(0,50)}</td>
                    <td><span class="badge bg-${h.status=='Sent'?'success':'danger'}">${h.status}</span></td>
                    <td><span class="badge bg-info">${h.delay_used || 8}s</span></td>
                </tr>`;
            });
            document.getElementById('historyTable tbody').innerHTML = html;
        }
        
        function selectContact(number) {
            document.getElementById('singleNumber').value = number;
            bootstrap.Modal.getInstance(document.getElementById('contactListModal')).hide();
            document.querySelector('[data-bs-target="#send"]').click();
        }
        
        function showAddContact() { new bootstrap.Modal(document.getElementById('contactModal')).show(); }
        function showAddGroup() { new bootstrap.Modal(document.getElementById('groupModal')).show(); }
        function showAddTemplate() { new bootstrap.Modal(document.getElementById('templateModal')).show(); }
        function showContactList() { loadContactsForSelector(); new bootstrap.Modal(document.getElementById('contactListModal')).show(); }
        
        async function loadContactsForSelector() {
            let contacts = await fetch('/api/contacts').then(r=>r.json());
            let html = '';
            contacts.forEach(c => {
                html += `<div class="number-list-item" onclick="selectContact('${c.number}')"><strong>${c.name}</strong><br><small>${c.number}</small></div>`;
            });
            document.getElementById('contactSelector').innerHTML = html;
        }
        
        function selectQuickNumber() {
            let select = document.getElementById('quickNumber');
            document.getElementById('singleNumber').value = select.value;
        }
        
        async function addContact() {
            let contact = {
                name: document.getElementById('contactName').value,
                number: document.getElementById('contactNumber').value,
                group: document.getElementById('contactGroup').value
            };
            await fetch('/api/contacts', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(contact)});
            bootstrap.Modal.getInstance(document.getElementById('contactModal')).hide();
            loadContacts();
        }
        
        async function createGroup() {
            let name = document.getElementById('groupName').value;
            await fetch('/api/groups', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name})});
            bootstrap.Modal.getInstance(document.getElementById('groupModal')).hide();
            loadGroups();
        }
        
        async function addTemplate() {
            let template = {
                name: document.getElementById('templateName').value,
                content: document.getElementById('templateContent').value
            };
            await fetch('/api/templates', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(template)});
            bootstrap.Modal.getInstance(document.getElementById('templateModal')).hide();
            loadTemplates();
        }
        
        function useTemplate(content) {
            document.getElementById('singleMessage').value = content;
            document.getElementById('singleMessage').focus();
            document.querySelector('[data-bs-target="#send"]').click();
        }
        
        async function deleteContact(id) {
            if(confirm('Delete this contact?')) {
                await fetch(`/api/contacts?id=${id}`, {method:'DELETE'});
                loadContacts();
            }
        }
        
        async function deleteGroup(id) {
            if(confirm('Delete this group?')) {
                await fetch(`/api/groups?id=${id}`, {method:'DELETE'});
                loadGroups();
            }
        }
        
        async function deleteTemplate(id) {
            if(confirm('Delete this template?')) {
                await fetch(`/api/templates?id=${id}`, {method:'DELETE'});
                loadTemplates();
            }
        }
        
        function saveAsTemplate() {
            let message = document.getElementById('singleMessage').value;
            if(!message) { alert('Write a message first'); return; }
            document.getElementById('templateName').value = 'Quick Template';
            document.getElementById('templateContent').value = message;
            new bootstrap.Modal(document.getElementById('templateModal')).show();
        }
        
        function exportHistory() {
            window.open('/api/export-history', '_blank');
        }
        
        function copyAPIKey() {
            navigator.clipboard.writeText('{{ api_key }}');
            alert('API Key copied!');
        }
        
        function logout() {
            window.location.href = '/logout';
        }
        
        document.getElementById('singleMessage').addEventListener('input', function() {
            document.getElementById('charCount').innerText = this.value.length + ' / 160 characters';
        });
        
        // Load initial data
        loadDashboard();
        loadContacts();
        loadGroups();
        loadTemplates();
        loadHistory();
        
        // Load quick numbers
        setTimeout(async () => {
            let contacts = await fetch('/api/contacts').then(r=>r.json());
            let select = document.getElementById('quickNumber');
            contacts.forEach(c => {
                let option = document.createElement('option');
                option.value = c.number;
                option.text = `${c.name} (${c.number})`;
                select.appendChild(option);
            });
        }, 1000);
    </script>
</body>
</html>
'''

# Flask Routes
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == ADMIN_USERNAME and request.form['password'] == ADMIN_PASSWORD:
            session['logged_in'] = True
            return render_template_string(DASHBOARD_HTML, api_key=API_KEY)
        return '<h3>Invalid credentials!</h3><a href="/">Try again</a>'
    
    if session.get('logged_in'):
        return render_template_string(DASHBOARD_HTML, api_key=API_KEY)
    return '''
    <!DOCTYPE html>
    <html>
    <head><title>Login</title><style>
        body{background:linear-gradient(135deg,#667eea,#764ba2);font-family:Arial;display:flex;justify-content:center;align-items:center;height:100vh;}
        .card{background:white;padding:40px;border-radius:20px;width:350px;}
        input{width:100%;padding:12px;margin:10px 0;border:2px solid #e0e0e0;border-radius:10px;}
        button{width:100%;background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:12px;border:none;border-radius:10px;cursor:pointer;}
    </style></head>
    <body>
        <div class="card"><h2>SMS Pro</h2>
        <form method="POST"><input name="username" placeholder="Username"><input type="password" name="password" placeholder="Password"><button type="submit">Login</button></form></div>
    </body>
    </html>
    '''

@app.route('/logout')
def logout():
    session.clear()
    return '<a href="/">Login again</a>'

@app.route('/api/send', methods=['POST'])
def api_send():
    data = request.json
    if data.get('key') != API_KEY:
        return jsonify({"error": "Invalid API key"}), 403
    
    number, message = data.get('number'), data.get('message')
    delay = data.get('delay', SMS_DELAY_SECONDS)
    
    if not number or not message:
        return jsonify({"error": "Missing fields"}), 400
    
    # Apply delay if specified
    if delay > 0:
        time.sleep(delay)
    
    success, result = send_sms(number, message)
    
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    c.execute("INSERT INTO messages (number, message, status, timestamp, sender_ip, delay_used) VALUES (?,?,?,?,?,?)",
              (number, message, 'Sent' if success else result, datetime.datetime.now(), request.remote_addr, delay))
    conn.commit()
    conn.close()
    
    return jsonify({"success": success, "message": result})

@app.route('/api/bulk', methods=['POST'])
def api_bulk():
    data = request.json
    if data.get('key') != API_KEY:
        return jsonify({"error": "Invalid API key"}), 403
    
    numbers = data.get('numbers', [])
    message = data.get('message')
    delay = data.get('delay', SMS_DELAY_SECONDS)
    
    # Start background thread for bulk sending
    def process_bulk():
        send_bulk_with_delay(numbers, message, delay)
    
    thread = threading.Thread(target=process_bulk)
    thread.start()
    
    return jsonify({"success": True, "message": f"Bulk send started for {len(numbers)} numbers with {delay}s delay"})

@app.route('/api/contacts', methods=['GET', 'POST', 'DELETE'])
def manage_contacts():
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    if request.method == 'POST':
        data = request.json
        c.execute("INSERT INTO contacts (name, number, group_name, created) VALUES (?,?,?,?)",
                  (data['name'], data['number'], data.get('group'), datetime.datetime.now()))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    if request.method == 'DELETE':
        contact_id = request.args.get('id')
        c.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    c.execute("SELECT id, name, number, group_name FROM contacts ORDER BY name")
    contacts = [{"id": row[0], "name": row[1], "number": row[2], "group_name": row[3]} for row in c.fetchall()]
    conn.close()
    return jsonify(contacts)

@app.route('/api/groups', methods=['GET', 'POST', 'DELETE'])
def manage_groups():
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    if request.method == 'POST':
        data = request.json
        c.execute("INSERT INTO groups (name, created) VALUES (?,?)", (data['name'], datetime.datetime.now()))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    if request.method == 'DELETE':
        group_id = request.args.get('id')
        c.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    c.execute("SELECT id, name FROM groups")
    groups = [{"id": row[0], "name": row[1]} for row in c.fetchall()]
    conn.close()
    return jsonify(groups)

@app.route('/api/group-contacts/<int:group_id>')
def get_group_contacts(group_id):
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    c.execute("SELECT name, number FROM contacts WHERE group_name = (SELECT name FROM groups WHERE id=?)", (group_id,))
    contacts = [{"name": row[0], "number": row[1]} for row in c.fetchall()]
    conn.close()
    return jsonify(contacts)

@app.route('/api/templates', methods=['GET', 'POST', 'DELETE'])
def manage_templates():
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    if request.method == 'POST':
        data = request.json
        c.execute("INSERT INTO templates (name, content, created) VALUES (?,?,?)",
                  (data['name'], data['content'], datetime.datetime.now()))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    if request.method == 'DELETE':
        template_id = request.args.get('id')
        c.execute("DELETE FROM templates WHERE id = ?", (template_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    c.execute("SELECT id, name, content FROM templates")
    templates = [{"id": row[0], "name": row[1], "content": row[2]} for row in c.fetchall()]
    conn.close()
    return jsonify(templates)

@app.route('/api/history')
def get_history():
    limit = request.args.get('limit', 100)
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    c.execute(f"SELECT timestamp, number, message, status, delay_used FROM messages ORDER BY timestamp DESC LIMIT {limit}")
    history = [{"timestamp": row[0], "number": row[1], "message": row[2], "status": row[3], "delay_used": row[4] or 8} for row in c.fetchall()]
    conn.close()
    return jsonify({"history": history})

@app.route('/api/stats')
def get_stats():
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM messages WHERE date(timestamp) = date('now')")
    today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM messages WHERE status = 'Sent'")
    success = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM contacts")
    contacts = c.fetchone()[0]
    success_rate = round((success / total * 100), 1) if total > 0 else 0
    conn.close()
    return jsonify({"total": total, "today": today, "success_rate": success_rate, "contacts": contacts})

@app.route('/api/chart-data')
def chart_data():
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    c.execute("SELECT date(timestamp) as day, COUNT(*) FROM messages WHERE date(timestamp) >= date('now', '-7 days') GROUP BY day")
    data = c.fetchall()
    conn.close()
    labels = [row[0] for row in data]
    values = [row[1] for row in data]
    return jsonify({"labels": labels, "values": values})

@app.route('/api/export-history')
def export_history():
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    c.execute("SELECT timestamp, number, message, status FROM messages ORDER BY timestamp DESC")
    data = c.fetchall()
    conn.close()
    
    import csv
    from io import StringIO
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Timestamp', 'Number', 'Message', 'Status'])
    writer.writerows(data)
    output.seek(0)
    
    from flask import Response
    return Response(output.getvalue(), mimetype='text/csv', headers={"Content-Disposition": "attachment;filename=sms_history.csv"})

if __name__ == '__main__':
    print("="*60)
    print("🚀 SMS ULTRA PRO - With Delay Control")
    print("="*60)
    print(f"📱 Local URL: http://localhost:8080")
    print(f"🔑 API Key: {API_KEY}")
    print(f"👤 Admin: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
    print("="*60)
    print("✨ NEW FEATURES:")
    print("  • ⏰ 8-Second Delay Between Messages")
    print("  • 📊 Real-time Bulk Progress")
    print("  • ⏹️ Stop Bulk Operation Anytime")
    print("  • 📈 Estimated Time Calculator")
    print("  • 🎚️ Adjustable Delay Slider (1-30s)")
    print("  • 📋 Copy/Paste Numbers List")
    print("  • 💾 Export History to CSV")
    print("="*60)
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)
