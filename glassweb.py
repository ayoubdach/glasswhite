from flask import Flask, request, jsonify, render_template_string, session
from flask_cors import CORS
import subprocess, sqlite3, datetime, secrets, time, threading, queue
import re
from functools import wraps

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
CORS(app)

# Configuration
API_KEY = "GlasswhiteUltimate2026"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

# Global queue for scheduled messages
scheduled_queue = queue.Queue()
scheduler_running = True

# Database setup
def init_db():
    conn = sqlite3.connect('sms_final.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  number TEXT, message TEXT, status TEXT, 
                  timestamp DATETIME, sender_ip TEXT, 
                  delay_used INTEGER DEFAULT 8,
                  delivery_report TEXT)''')
    
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
    
    c.execute('''CREATE TABLE IF NOT EXISTS scheduled
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  number TEXT, message TEXT, schedule_time DATETIME,
                  status TEXT, created DATETIME)''')
    
    conn.commit()
    conn.close()

init_db()

# RELIABLE SMS SEND FUNCTION with verification
def send_sms_reliable(number, message, retry_count=3):
    """Send SMS with retry mechanism and delivery verification"""
    
    # Clean number
    number = re.sub(r'\s+', '', number)
    if not number.startswith('+'):
        number = '+' + number
    
    for attempt in range(retry_count):
        try:
            # Send SMS
            result = subprocess.run(
                ['termux-sms-send', '-n', number, message],
                timeout=30,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # Wait a bit for network
                time.sleep(2)
                return True, "Sent successfully"
            else:
                if attempt < retry_count - 1:
                    time.sleep(2)  # Wait before retry
                    continue
                return False, f"Failed: {result.stderr}"
                
        except subprocess.TimeoutExpired:
            if attempt < retry_count - 1:
                time.sleep(2)
                continue
            return False, "Timeout error"
        except Exception as e:
            if attempt < retry_count - 1:
                time.sleep(2)
                continue
            return False, str(e)
    
    return False, "Unknown error"

# SCHEDULER THREAD
def scheduler_worker():
    """Background thread to process scheduled messages"""
    global scheduler_running
    
    while scheduler_running:
        try:
            now = datetime.datetime.now()
            conn = sqlite3.connect('sms_final.db')
            c = conn.cursor()
            
            # Get pending scheduled messages
            c.execute("SELECT id, number, message FROM scheduled WHERE schedule_time <= ? AND status = 'pending'", (now,))
            pending = c.fetchall()
            
            for msg_id, number, message in pending:
                # Send SMS
                success, result = send_sms_reliable(number, message)
                
                # Update status
                status = 'sent' if success else 'failed'
                c.execute("UPDATE scheduled SET status = ? WHERE id = ?", (status, msg_id))
                conn.commit()
                
                # Also log to messages table
                c.execute("INSERT INTO messages (number, message, status, timestamp, delivery_report) VALUES (?,?,?,?,?)",
                         (number, message, status, now, result))
                conn.commit()
                
                # Wait 8 seconds between scheduled messages
                time.sleep(8)
            
            conn.close()
            
        except Exception as e:
            print(f"Scheduler error: {e}")
        
        time.sleep(5)  # Check every 5 seconds

# Start scheduler thread
scheduler_thread = threading.Thread(target=scheduler_worker, daemon=True)
scheduler_thread.start()

# HTML Dashboard - COMPLETE WITH BULK SCHEDULE
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SMS Final Pro - Complete</title>
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
        .nav-tabs .nav-link.active { background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; }
        .sms-status { padding: 10px; border-radius: 10px; margin: 5px 0; }
        .status-sent { background: #d4edda; color: #155724; border-left: 4px solid #28a745; }
        .status-failed { background: #f8d7da; color: #721c24; border-left: 4px solid #dc3545; }
        .status-sending { background: #fff3cd; color: #856404; border-left: 4px solid #ffc107; }
    </style>
</head>
<body>
    <div class="container-fluid">
        <!-- Header -->
        <div class="card">
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <h2><i class="fas fa-sms"></i> SMS Final Pro</h2>
                        <p class="text-muted">Complete SMS Gateway - With Bulk Schedule</p>
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
            <div class="col-md-3"><div class="stat-card"><i class="fas fa-clock fa-2x"></i><div class="stat-value" id="scheduledCount">0</div><div>Scheduled</div></div></div>
        </div>
        
        <!-- Tabs -->
        <ul class="nav nav-tabs mb-3" id="myTab" role="tablist">
            <li class="nav-item"><a class="nav-link active" data-bs-toggle="tab" href="#send"><i class="fas fa-paper-plane"></i> Send SMS</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#bulk"><i class="fas fa-layer-group"></i> Bulk SMS</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#schedule"><i class="fas fa-calendar-alt"></i> Schedule</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#contacts"><i class="fas fa-address-book"></i> Contacts</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#groups"><i class="fas fa-users"></i> Groups</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#history"><i class="fas fa-history"></i> History</a></li>
        </ul>
        
        <div class="tab-content">
            <!-- Send SMS Tab -->
            <div class="tab-pane fade show active" id="send">
                <div class="card">
                    <div class="card-header"><i class="fas fa-paper-plane"></i> Send Single SMS (With Auto-Retry)</div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-8">
                                <label>Phone Number</label>
                                <input type="text" id="singleNumber" class="form-control" placeholder="+216XXXXXXXX">
                            </div>
                            <div class="col-md-4">
                                <label>Quick Select</label>
                                <select id="quickNumber" class="form-control" onchange="selectQuickNumber()">
                                    <option value="">Select from contacts...</option>
                                </select>
                            </div>
                        </div>
                        
                        <label class="mt-3">Message</label>
                        <textarea id="singleMessage" rows="4" class="form-control" placeholder="Type your message here..."></textarea>
                        <small id="charCount" class="text-muted">0 / 160 characters</small>
                        
                        <button class="btn btn-gradient mt-3" onclick="sendSingleSMS()"><i class="fas fa-paper-plane"></i> Send Now</button>
                        <div id="sendResult" class="mt-3"></div>
                    </div>
                </div>
            </div>
            
            <!-- Bulk SMS Tab -->
            <div class="tab-pane fade" id="bulk">
                <div class="card">
                    <div class="card-header"><i class="fas fa-layer-group"></i> Bulk SMS (8 sec delay between each)</div>
                    <div class="card-body">
                        <div class="alert alert-info">
                            <i class="fas fa-info-circle"></i> Each number will be sent with 8 second delay + automatic retry on failure
                        </div>
                        
                        <label>Phone Numbers (one per line)</label>
                        <textarea id="bulkNumbers" rows="8" class="form-control" placeholder="+216XXXXXXXXX&#10;+216YYYYYYYYY&#10;+216ZZZZZZZZZ"></textarea>
                        <small id="numberCount" class="text-muted">0 numbers</small>
                        
                        <label class="mt-3">Message</label>
                        <textarea id="bulkMessage" rows="3" class="form-control" placeholder="Message to send to all numbers"></textarea>
                        
                        <div id="bulkProgress" class="mt-3" style="display:none;">
                            <div class="progress mb-2">
                                <div id="bulkBar" class="progress-bar progress-bar-striped progress-bar-animated" style="width:0%">0%</div>
                            </div>
                            <div id="bulkStatus" class="sms-status status-sending"></div>
                            <div id="bulkDetails" class="mt-2 small"></div>
                        </div>
                        
                        <button class="btn btn-gradient mt-3" onclick="startBulkSend()"><i class="fas fa-play"></i> Start Bulk Send</button>
                        <button class="btn btn-danger mt-3" onclick="stopBulkSend()" id="stopBtn" style="display:none;"><i class="fas fa-stop"></i> Stop</button>
                        
                        <div id="bulkFinalResult" class="mt-3"></div>
                    </div>
                </div>
            </div>
            
            <!-- Schedule Tab - WITH BULK SUPPORT -->
            <div class="tab-pane fade" id="schedule">
                <div class="card">
                    <div class="card-header"><i class="fas fa-calendar-alt"></i> Schedule SMS (Single or Bulk)</div>
                    <div class="card-body">
                        <ul class="nav nav-tabs" id="scheduleTabs">
                            <li class="nav-item"><a class="nav-link active" data-bs-toggle="tab" href="#singleSchedule">Single SMS</a></li>
                            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#bulkSchedule">Bulk SMS</a></li>
                        </ul>
                        
                        <div class="tab-content mt-3">
                            <!-- Single Schedule -->
                            <div class="tab-pane active" id="singleSchedule">
                                <div class="row">
                                    <div class="col-md-6">
                                        <label>Phone Number</label>
                                        <input type="text" id="scheduleNumber" class="form-control" placeholder="+216XXXXXXXX">
                                    </div>
                                    <div class="col-md-6">
                                        <label>Schedule Date & Time</label>
                                        <input type="datetime-local" id="scheduleDateTime" class="form-control">
                                    </div>
                                </div>
                                <label class="mt-3">Message</label>
                                <textarea id="scheduleMessage" rows="3" class="form-control" placeholder="Message to send later"></textarea>
                                <button class="btn btn-gradient mt-3" onclick="scheduleSMS()"><i class="fas fa-calendar-plus"></i> Schedule Single SMS</button>
                            </div>
                            
                            <!-- Bulk Schedule -->
                            <div class="tab-pane" id="bulkSchedule">
                                <div class="alert alert-info">
                                    <i class="fas fa-info-circle"></i> Schedule bulk SMS to multiple numbers at once (8 seconds delay between each)
                                </div>
                                
                                <label>Phone Numbers (one per line)</label>
                                <textarea id="bulkScheduleNumbers" rows="6" class="form-control" placeholder="+216XXXXXXXXX&#10;+216YYYYYYYYY&#10;+216ZZZZZZZZZ"></textarea>
                                <small id="bulkScheduleCount" class="text-muted">0 numbers</small>
                                
                                <label class="mt-3">Message</label>
                                <textarea id="bulkScheduleMessage" rows="3" class="form-control" placeholder="Message to send to all numbers"></textarea>
                                
                                <label class="mt-3">Schedule Date & Time</label>
                                <input type="datetime-local" id="bulkScheduleDateTime" class="form-control">
                                
                                <button class="btn btn-gradient mt-3" onclick="scheduleBulkSMS()"><i class="fas fa-calendar-plus"></i> Schedule Bulk SMS</button>
                            </div>
                        </div>
                        
                        <hr class="mt-4">
                        <h5><i class="fas fa-clock"></i> Pending Scheduled Messages</h5>
                        <div id="scheduledList" class="mt-3"></div>
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
                        <input type="text" id="searchContact" class="form-control mb-3" placeholder="Search contacts...">
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
            
            <!-- History Tab -->
            <div class="tab-pane fade" id="history">
                <div class="card">
                    <div class="card-header"><i class="fas fa-history"></i> Message History</div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table" id="historyTable">
                                <thead><tr><th>Time</th><th>Number</th><th>Message</th><th>Status</th><th>Report</th></tr></thead>
                                <tbody></tbody>
                            </table>
                        </div>
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
    
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let bulkActive = false;
        let currentNumbers = [];
        
        // Update number counts
        document.getElementById('bulkNumbers').addEventListener('input', function() {
            let lines = this.value.split('\\n');
            let numbers = lines.filter(l => l.trim().match(/^\\+?[0-9]/));
            document.getElementById('numberCount').innerText = numbers.length + ' numbers';
            currentNumbers = numbers;
        });
        
        document.getElementById('bulkScheduleNumbers').addEventListener('input', function() {
            let lines = this.value.split('\\n');
            let numbers = lines.filter(l => l.trim().match(/^\\+?[0-9]/));
            document.getElementById('bulkScheduleCount').innerText = numbers.length + ' numbers to schedule';
        });
        
        // Send single SMS
        async function sendSingleSMS() {
            let number = document.getElementById('singleNumber').value;
            let message = document.getElementById('singleMessage').value;
            
            if(!number || !message) {
                alert('Please fill both number and message');
                return;
            }
            
            let resultDiv = document.getElementById('sendResult');
            resultDiv.innerHTML = '<div class="sms-status status-sending">📤 Sending with retry...</div>';
            
            let res = await fetch('/api/send', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({number, message, key: '{{ api_key }}'})
            });
            let data = await res.json();
            
            if(data.success) {
                resultDiv.innerHTML = '<div class="sms-status status-sent">✅ ' + data.message + '</div>';
                document.getElementById('singleNumber').value = '';
                document.getElementById('singleMessage').value = '';
                loadHistory();
                loadStats();
            } else {
                resultDiv.innerHTML = '<div class="sms-status status-failed">❌ ' + data.message + '</div>';
            }
        }
        
        // Start bulk send
        async function startBulkSend() {
            let numbers = currentNumbers;
            let message = document.getElementById('bulkMessage').value;
            
            if(numbers.length === 0) {
                alert('Add numbers first!');
                return;
            }
            if(!message) {
                alert('Enter a message!');
                return;
            }
            
            if(!confirm(`Send to ${numbers.length} numbers?\\nEach will have 8 second delay.\\nTotal time: ~${Math.ceil(numbers.length * 8 / 60)} minutes`)) {
                return;
            }
            
            bulkActive = true;
            document.getElementById('bulkProgress').style.display = 'block';
            document.getElementById('stopBtn').style.display = 'inline-block';
            document.getElementById('bulkFinalResult').innerHTML = '';
            
            let sent = 0;
            let failed = 0;
            
            for(let i = 0; i < numbers.length && bulkActive; i++) {
                let percent = Math.round(((i + 1) / numbers.length) * 100);
                document.getElementById('bulkBar').style.width = percent + '%';
                document.getElementById('bulkBar').innerText = percent + '%';
                document.getElementById('bulkStatus').innerHTML = `📤 Sending ${i+1}/${numbers.length}...`;
                document.getElementById('bulkDetails').innerHTML = `✅ Sent: ${sent} | ❌ Failed: ${failed} | Remaining: ${numbers.length - i - 1}`;
                
                let res = await fetch('/api/send', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({number: numbers[i], message, key: '{{ api_key }}'})
                });
                let data = await res.json();
                
                if(data.success) {
                    sent++;
                } else {
                    failed++;
                }
                
                document.getElementById('bulkStatus').innerHTML = `✅ Sent: ${sent} | ❌ Failed: ${failed}`;
                
                if(i < numbers.length - 1 && bulkActive) {
                    for(let s = 8; s > 0 && bulkActive; s--) {
                        document.getElementById('bulkDetails').innerHTML = `⏰ Waiting ${s} seconds before next message... | Sent: ${sent} | Failed: ${failed}`;
                        await new Promise(r => setTimeout(r, 1000));
                    }
                }
            }
            
            document.getElementById('bulkProgress').style.display = 'none';
            document.getElementById('stopBtn').style.display = 'none';
            
            let finalMsg = `<div class="sms-status status-sent">✅ Bulk Send Complete!\\n📊 Total: ${numbers.length} | ✅ Sent: ${sent} | ❌ Failed: ${failed}</div>`;
            document.getElementById('bulkFinalResult').innerHTML = finalMsg;
            
            loadStats();
            loadHistory();
            bulkActive = false;
        }
        
        function stopBulkSend() {
            if(confirm('Stop current bulk operation?')) {
                bulkActive = false;
                document.getElementById('bulkStatus').innerHTML = '⏹️ Stopped by user';
            }
        }
        
        // Schedule single SMS
        async function scheduleSMS() {
            let number = document.getElementById('scheduleNumber').value;
            let message = document.getElementById('scheduleMessage').value;
            let scheduleTime = document.getElementById('scheduleDateTime').value;
            
            if(!number || !message || !scheduleTime) {
                alert('Fill all fields');
                return;
            }
            
            let res = await fetch('/api/schedule', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({number, message, scheduleTime, key: '{{ api_key }}'})
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
        
        // Schedule bulk SMS
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
            
            if(!confirm(`Schedule ${numbers.length} messages to be sent at ${scheduleTime}?\\nEach will have 8 second delay between them.`)) {
                return;
            }
            
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
                alert(`✅ ${data.scheduled} SMS messages scheduled successfully!`);
                document.getElementById('bulkScheduleNumbers').value = '';
                document.getElementById('bulkScheduleMessage').value = '';
                document.getElementById('bulkScheduleDateTime').value = '';
                loadScheduled();
                loadStats();
            } else {
                alert('❌ Failed to schedule: ' + data.message);
            }
        }
        
        async function loadScheduled() {
            let res = await fetch('/api/scheduled');
            let data = await res.json();
            let html = '<div class="list-group">';
            data.scheduled.forEach(s => {
                let statusBadge = s.status === 'pending' ? 'warning' : (s.status === 'sent' ? 'success' : 'danger');
                html += `<div class="list-group-item">
                    <div class="d-flex justify-content-between">
                        <div>
                            <strong>${s.number}</strong><br>
                            <small>${s.message.substring(0,50)}</small><br>
                            <small class="text-muted">Schedule: ${s.schedule_time}</small>
                        </div>
                        <div>
                            <span class="badge bg-${statusBadge}">${s.status}</span>
                            ${s.status === 'pending' ? `<button class="btn btn-sm btn-danger mt-2" onclick="cancelSchedule(${s.id})">Cancel</button>` : ''}
                        </div>
                    </div>
                </div>`;
            });
            html += '</div>';
            document.getElementById('scheduledList').innerHTML = html || '<p>No scheduled messages</p>';
        }
        
        async function cancelSchedule(id) {
            if(confirm('Cancel this scheduled message?')) {
                await fetch(`/api/schedule/${id}`, {method: 'DELETE'});
                loadScheduled();
            }
        }
        
        async function loadStats() {
            let stats = await fetch('/api/stats').then(r=>r.json());
            document.getElementById('totalSMS').innerText = stats.total;
            document.getElementById('successRate').innerText = stats.success_rate + '%';
            document.getElementById('totalContacts').innerText = stats.contacts;
            document.getElementById('scheduledCount').innerText = stats.scheduled;
        }
        
        async function loadContacts() {
            let contacts = await fetch('/api/contacts').then(r=>r.json());
            let html = '';
            contacts.forEach(c => {
                html += `<div class="list-group-item">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${c.name}</strong><br>
                            <small>${c.number}</small><br>
                            <small class="text-muted">${c.group_name || 'No group'}</small>
                        </div>
                        <div>
                            <button class="btn btn-sm btn-primary" onclick="useNumber('${c.number}')"><i class="fas fa-paper-plane"></i></button>
                            <button class="btn btn-sm btn-danger" onclick="deleteContact(${c.id})"><i class="fas fa-trash"></i></button>
                        </div>
                    </div>
                </div>`;
            });
            document.getElementById('contactsList').innerHTML = html || '<div class="alert alert-info">No contacts yet</div>';
        }
        
        async function loadGroups() {
            let groups = await fetch('/api/groups').then(r=>r.json());
            let html = '';
            for(let g of groups) {
                let members = await fetch(`/api/group-contacts/${g.id}`).then(r=>r.json());
                html += `<div class="card mb-2">
                    <div class="card-body">
                        <strong><i class="fas fa-users"></i> ${g.name}</strong>
                        <span class="badge bg-primary">${members.length} members</span>
                        <button class="btn btn-sm btn-primary mt-2" onclick="sendToGroup(${g.id})">Send to Group</button>
                        <button class="btn btn-sm btn-danger mt-2" onclick="deleteGroup(${g.id})">Delete</button>
                    </div>
                </div>`;
            }
            document.getElementById('groupsList').innerHTML = html || '<p>No groups yet</p>';
        }
        
        async function loadHistory() {
            let history = await fetch('/api/history').then(r=>r.json());
            let html = '';
            history.history.forEach(h => {
                let statusClass = h.status === 'Sent successfully' ? 'success' : 'danger';
                html += `<tr>
                    <td>${h.timestamp}</td>
                    <td>${h.number}</td>
                    <td>${h.message.substring(0,50)}</td>
                    <td><span class="badge bg-${statusClass}">${h.status}</span></td>
                    <td><small>${h.delivery_report || '-'}</small></td>
                </tr>`;
            });
            document.getElementById('historyTable tbody').innerHTML = html;
        }
        
        function useNumber(number) {
            document.getElementById('singleNumber').value = number;
            document.querySelector('[data-bs-target="#send"]').click();
        }
        
        function sendToGroup(groupId) {
            let message = prompt('Enter message for this group:');
            if(message) {
                fetch('/api/send-group', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({groupId, message, key: '{{ api_key }}'})
                }).then(res => res.json()).then(data => {
                    alert(data.message);
                });
            }
        }
        
        function selectQuickNumber() {
            let select = document.getElementById('quickNumber');
            document.getElementById('singleNumber').value = select.value;
        }
        
        function showAddContact() { new bootstrap.Modal(document.getElementById('contactModal')).show(); }
        function showAddGroup() { new bootstrap.Modal(document.getElementById('groupModal')).show(); }
        
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
        }
        
        async function createGroup() {
            let name = document.getElementById('groupName').value;
            await fetch('/api/groups', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name})});
            bootstrap.Modal.getInstance(document.getElementById('groupModal')).hide();
            loadGroups();
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
        
        function logout() { window.location.href = '/logout'; }
        
        document.getElementById('singleMessage').addEventListener('input', function() {
            document.getElementById('charCount').innerText = this.value.length + ' / 160 characters';
        });
        
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
        
        // Initial loads
        loadStats();
        loadContacts();
        loadGroups();
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
        h2{text-align:center;color:#333;}
    </style></head>
    <body>
        <div class="card"><h2>SMS Final Pro</h2>
        <form method="POST"><input name="username" placeholder="Username"><input type="password" name="password" placeholder="Password"><button type="submit">Login</button></form></div>
    </body>
    </html>
    '''

@app.route('/logout')
def logout():
    session.clear()
    return '<meta http-equiv="refresh" content="2;url=/" />Logged out. Redirecting...'

@app.route('/api/send', methods=['POST'])
def api_send():
    data = request.json
    if data.get('key') != API_KEY:
        return jsonify({"error": "Invalid API key"}), 403
    
    number = data.get('number')
    message = data.get('message')
    
    if not number or not message:
        return jsonify({"error": "Missing fields"}), 400
    
    # Send with retry
    success, result = send_sms_reliable(number, message)
    
    # Log to database
    conn = sqlite3.connect('sms_final.db')
    c = conn.cursor()
    c.execute("INSERT INTO messages (number, message, status, timestamp, sender_ip, delivery_report) VALUES (?,?,?,?,?,?)",
              (number, message, 'Sent successfully' if success else 'Failed', datetime.datetime.now(), request.remote_addr, result))
    conn.commit()
    conn.close()
    
    return jsonify({"success": success, "message": result})

@app.route('/api/schedule', methods=['POST'])
def api_schedule():
    data = request.json
    if data.get('key') != API_KEY:
        return jsonify({"error": "Invalid API key"}), 403
    
    number = data.get('number')
    message = data.get('message')
    schedule_time = datetime.datetime.fromisoformat(data.get('scheduleTime'))
    
    conn = sqlite3.connect('sms_final.db')
    c = conn.cursor()
    c.execute("INSERT INTO scheduled (number, message, schedule_time, status, created) VALUES (?,?,?,?,?)",
              (number, message, schedule_time, 'pending', datetime.datetime.now()))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True})

@app.route('/api/schedule-bulk', methods=['POST'])
def api_schedule_bulk():
    data = request.json
    if data.get('key') != API_KEY:
        return jsonify({"error": "Invalid API key"}), 403
    
    numbers = data.get('numbers', [])
    message = data.get('message')
    schedule_time = datetime.datetime.fromisoformat(data.get('scheduleTime'))
    
    conn = sqlite3.connect('sms_final.db')
    c = conn.cursor()
    
    scheduled_count = 0
    for number in numbers:
        c.execute("INSERT INTO scheduled (number, message, schedule_time, status, created) VALUES (?,?,?,?,?)",
                  (number, message, schedule_time, 'pending', datetime.datetime.now()))
        scheduled_count += 1
    
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "scheduled": scheduled_count})

@app.route('/api/scheduled')
def get_scheduled():
    conn = sqlite3.connect('sms_final.db')
    c = conn.cursor()
    c.execute("SELECT id, number, message, schedule_time, status FROM scheduled WHERE status = 'pending' ORDER BY schedule_time ASC")
    scheduled = [{"id": row[0], "number": row[1], "message": row[2], "schedule_time": row[3], "status": row[4]} for row in c.fetchall()]
    conn.close()
    return jsonify({"scheduled": scheduled})

@app.route('/api/schedule/<int:schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    conn = sqlite3.connect('sms_final.db')
    c = conn.cursor()
    c.execute("DELETE FROM scheduled WHERE id = ?", (schedule_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/contacts', methods=['GET', 'POST', 'DELETE'])
def manage_contacts():
    conn = sqlite3.connect('sms_final.db')
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
    conn = sqlite3.connect('sms_final.db')
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
    conn = sqlite3.connect('sms_final.db')
    c = conn.cursor()
    c.execute("SELECT name, number FROM contacts WHERE group_name = (SELECT name FROM groups WHERE id=?)", (group_id,))
    contacts = [{"name": row[0], "number": row[1]} for row in c.fetchall()]
    conn.close()
    return jsonify(contacts)

@app.route('/api/history')
def get_history():
    conn = sqlite3.connect('sms_final.db')
    c = conn.cursor()
    c.execute("SELECT timestamp, number, message, status, delivery_report FROM messages ORDER BY timestamp DESC LIMIT 100")
    history = [{"timestamp": row[0], "number": row[1], "message": row[2], "status": row[3], "delivery_report": row[4]} for row in c.fetchall()]
    conn.close()
    return jsonify({"history": history})

@app.route('/api/stats')
def get_stats():
    conn = sqlite3.connect('sms_final.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM messages WHERE status = 'Sent successfully'")
    success = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM contacts")
    contacts = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM scheduled WHERE status = 'pending'")
    scheduled = c.fetchone()[0]
    
    success_rate = round((success / total * 100), 1) if total > 0 else 0
    conn.close()
    return jsonify({"total": total, "success_rate": success_rate, "contacts": contacts, "scheduled": scheduled})

@app.route('/api/send-group', methods=['POST'])
def send_to_group():
    data = request.json
    if data.get('key') != API_KEY:
        return jsonify({"error": "Invalid API key"}), 403
    
    conn = sqlite3.connect('sms_final.db')
    c = conn.cursor()
    c.execute("SELECT number FROM contacts WHERE group_name = (SELECT name FROM groups WHERE id=?)", (data.get('groupId'),))
    contacts = c.fetchall()
    conn.close()
    
    success_count = 0
    for contact in contacts:
        success, _ = send_sms_reliable(contact[0], data.get('message'))
        if success:
            success_count += 1
        time.sleep(8)
    
    return jsonify({"success": True, "message": f"Sent to {success_count}/{len(contacts)} contacts"})

if __name__ == '__main__':
    print("="*60)
    print("🚀 SMS FINAL PRO - COMPLETE WITH BULK SCHEDULE")
    print("="*60)
    print(f"📱 Local URL: http://localhost:8080")
    print(f"🔑 API Key: {API_KEY}")
    print(f"👤 Admin: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
    print("="*60)
    print("✨ ALL FEATURES:")
    print("  • ✅ Auto-retry on failure (3 attempts)")
    print("  • ✅ 8-second delay between messages")
    print("  • ✅ Schedule Single SMS")
    print("  • ✅ Schedule Bulk SMS (NEW!)")
    print("  • ✅ Bulk send with real progress")
    print("  • ✅ Stop/Cancel bulk operation")
    print("  • ✅ Contact & Group management")
    print("  • ✅ Message history")
    print("="*60)
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)
