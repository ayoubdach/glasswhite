from flask import Flask, request, jsonify, render_template_string, session, send_file
from flask_cors import CORS
import subprocess, sqlite3, datetime, secrets, csv, io, os
from functools import wraps
import pandas as pd
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
CORS(app)

# Configuration
API_KEY = "Glasswhite"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
UPLOAD_FOLDER = '/data/data/com.termux/files/home/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Enhanced Database
def init_db():
    conn = sqlite3.connect('sms_pro.db')
    c = conn.cursor()
    
    # Messages table
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  number TEXT, message TEXT, status TEXT, 
                  timestamp DATETIME, sender_ip TEXT, 
                  scheduled_time DATETIME, retry_count INTEGER DEFAULT 0)''')
    
    # Contacts table with groups
    c.execute('''CREATE TABLE IF NOT EXISTS contacts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT, number TEXT, group_name TEXT, 
                  email TEXT, notes TEXT, created DATETIME)''')
    
    # Templates table
    c.execute('''CREATE TABLE IF NOT EXISTS templates
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT, content TEXT, category TEXT, 
                  created DATETIME, usage_count INTEGER DEFAULT 0)''')
    
    # Groups table
    c.execute('''CREATE TABLE IF NOT EXISTS groups
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT, description TEXT, 
                  created DATETIME, total_members INTEGER DEFAULT 0)''')
    
    # Broadcast campaigns
    c.execute('''CREATE TABLE IF NOT EXISTS campaigns
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT, message TEXT, group_id INTEGER,
                  status TEXT, sent_count INTEGER DEFAULT 0,
                  total_count INTEGER DEFAULT 0,
                  created DATETIME, scheduled_time DATETIME)''')
    
    # Banned numbers
    c.execute('''CREATE TABLE IF NOT EXISTS blacklist
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  number TEXT UNIQUE, reason TEXT, 
                  created DATETIME)''')
    
    # API logs
    c.execute('''CREATE TABLE IF NOT EXISTS api_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  endpoint TEXT, ip TEXT, timestamp DATETIME,
                  status_code INTEGER)''')
    
    conn.commit()
    conn.close()

init_db()

# Send SMS with retry
def send_sms(number, message, retry=2):
    # Check blacklist
    conn = sqlite3.connect('sms_pro.db')
    c = conn.cursor()
    c.execute("SELECT id FROM blacklist WHERE number = ?", (number,))
    if c.fetchone():
        conn.close()
        return False, "Number is blacklisted"
    conn.close()
    
    for attempt in range(retry):
        try:
            subprocess.run(['termux-sms-send', '-n', number, message], 
                          timeout=15, check=True)
            return True, "Sent"
        except Exception as e:
            if attempt == retry - 1:
                return False, str(e)
    return False, "Failed"

# Validate number format
def validate_number(number):
    import re
    # Remove spaces and special chars
    number = re.sub(r'[\s\-\(\)]', '', number)
    # Check if starts with + or 00
    if not (number.startswith('+') or number.startswith('00')):
        return False, None
    return True, number

# HTML Template - ULTRA PRO VERSION
PRO_DASHBOARD = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SMS Ultra Pro - Advanced Gateway</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --primary: #667eea;
            --secondary: #764ba2;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
            --dark: #1f2937;
        }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .sidebar {
            position: fixed;
            left: 0;
            top: 0;
            height: 100%;
            width: 260px;
            background: white;
            box-shadow: 2px 0 10px rgba(0,0,0,0.1);
            transition: all 0.3s;
            z-index: 1000;
        }
        
        .sidebar-header {
            padding: 20px;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            color: white;
            text-align: center;
        }
        
        .sidebar-menu {
            padding: 20px 0;
        }
        
        .sidebar-menu a {
            display: block;
            padding: 12px 25px;
            color: var(--dark);
            text-decoration: none;
            transition: all 0.3s;
        }
        
        .sidebar-menu a:hover, .sidebar-menu a.active {
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            color: white;
        }
        
        .main-content {
            margin-left: 260px;
            padding: 20px;
        }
        
        .stat-card {
            background: white;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s;
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
        }
        
        .stat-icon {
            font-size: 40px;
            color: var(--primary);
        }
        
        .stat-value {
            font-size: 32px;
            font-weight: bold;
            margin: 10px 0;
        }
        
        .card {
            border: none;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        
        .card-header {
            background: white;
            border-bottom: 2px solid #f0f0f0;
            padding: 20px;
            font-weight: bold;
            border-radius: 15px 15px 0 0;
        }
        
        .btn-gradient {
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            color: white;
            border: none;
        }
        
        .btn-gradient:hover {
            transform: translateY(-2px);
            color: white;
        }
        
        .table-responsive {
            max-height: 400px;
            overflow-y: auto;
        }
        
        .badge-success {
            background: var(--success);
        }
        
        .badge-danger {
            background: var(--danger);
        }
        
        @media (max-width: 768px) {
            .sidebar {
                left: -260px;
            }
            .main-content {
                margin-left: 0;
            }
            .show-sidebar {
                left: 0;
            }
        }
        
        .toast-notification {
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 9999;
        }
        
        .progress-bar-gradient {
            background: linear-gradient(135deg, var(--primary), var(--secondary));
        }
        
        .number-list-item {
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .number-list-item:hover {
            background: #f0f0f0;
            transform: scale(1.02);
        }
    </style>
</head>
<body>
    <div class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <h4><i class="fas fa-sms"></i> SMS Ultra Pro</h4>
            <small>Advanced Gateway</small>
        </div>
        <div class="sidebar-menu">
            <a href="#" onclick="showSection('dashboard')" class="active">
                <i class="fas fa-chart-line"></i> Dashboard
            </a>
            <a href="#" onclick="showSection('send')">
                <i class="fas fa-paper-plane"></i> Send SMS
            </a>
            <a href="#" onclick="showSection('bulk')">
                <i class="fas fa-layer-group"></i> Bulk SMS
            </a>
            <a href="#" onclick="showSection('contacts')">
                <i class="fas fa-address-book"></i> Contacts
            </a>
            <a href="#" onclick="showSection('groups')">
                <i class="fas fa-users"></i> Groups
            </a>
            <a href="#" onclick="showSection('templates')">
                <i class="fas fa-file-alt"></i> Templates
            </a>
            <a href="#" onclick="showSection('campaigns')">
                <i class="fas fa-bullhorn"></i> Campaigns
            </a>
            <a href="#" onclick="showSection('history')">
                <i class="fas fa-history"></i> History
            </a>
            <a href="#" onclick="showSection('blacklist')">
                <i class="fas fa-ban"></i> Blacklist
            </a>
            <a href="#" onclick="showSection('analytics')">
                <i class="fas fa-chart-bar"></i> Analytics
            </a>
            <a href="#" onclick="showSection('api')">
                <i class="fas fa-code"></i> API Docs
            </a>
        </div>
    </div>
    
    <div class="main-content">
        <button class="btn btn-dark mb-3 d-md-none" onclick="toggleSidebar()">
            <i class="fas fa-bars"></i> Menu
        </button>
        
        <!-- Dashboard Section -->
        <div id="dashboardSection">
            <div class="row" id="statsRow">
                <div class="col-md-3">
                    <div class="stat-card">
                        <div class="stat-icon"><i class="fas fa-envelope"></i></div>
                        <div class="stat-value" id="totalSMS">-</div>
                        <div>Total SMS Sent</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stat-card">
                        <div class="stat-icon"><i class="fas fa-check-circle"></i></div>
                        <div class="stat-value" id="successRate">-</div>
                        <div>Success Rate</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stat-card">
                        <div class="stat-icon"><i class="fas fa-users"></i></div>
                        <div class="stat-value" id="totalContacts">-</div>
                        <div>Contacts</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stat-card">
                        <div class="stat-icon"><i class="fas fa-clock"></i></div>
                        <div class="stat-value" id="todaySMS">-</div>
                        <div>Today's SMS</div>
                    </div>
                </div>
            </div>
            
            <div class="row">
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">
                            <i class="fas fa-chart-line"></i> SMS Trends
                        </div>
                        <div class="card-body">
                            <canvas id="smsChart" height="200"></canvas>
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">
                            <i class="fas fa-list"></i> Recent Activity
                        </div>
                        <div class="card-body">
                            <div id="recentActivity"></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Send SMS Section -->
        <div id="sendSection" style="display:none;">
            <div class="card">
                <div class="card-header">
                    <i class="fas fa-paper-plane"></i> Send Single SMS
                </div>
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-8">
                            <label>Phone Number</label>
                            <div class="input-group">
                                <input type="text" id="singleNumber" class="form-control" placeholder="+216XXXXXXXX">
                                <button class="btn btn-secondary" onclick="showNumberSuggestions()">
                                    <i class="fas fa-list"></i> From Contacts
                                </button>
                            </div>
                            <small class="text-muted">Format: +21693517462</small>
                        </div>
                        <div class="col-md-4">
                            <label>Quick Select</label>
                            <select id="quickNumber" class="form-control" onchange="selectQuickNumber()">
                                <option value="">Select from list...</option>
                            </select>
                        </div>
                    </div>
                    
                    <div class="mt-3">
                        <label>Message</label>
                        <textarea id="singleMessage" rows="4" class="form-control" placeholder="Type your message here..."></textarea>
                        <small id="charCount" class="text-muted">0 / 160 characters</small>
                    </div>
                    
                    <div class="mt-3">
                        <label>Schedule (Optional)</label>
                        <input type="datetime-local" id="scheduleTime" class="form-control">
                    </div>
                    
                    <div class="mt-3">
                        <button class="btn btn-gradient" onclick="sendSingleSMS()">
                            <i class="fas fa-paper-plane"></i> Send Now
                        </button>
                        <button class="btn btn-secondary" onclick="saveAsTemplate()">
                            <i class="fas fa-save"></i> Save as Template
                        </button>
                    </div>
                    
                    <div id="sendResult" class="mt-3"></div>
                </div>
            </div>
            
            <!-- Number List Modal -->
            <div class="modal fade" id="numberListModal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">Select Contact</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <input type="text" id="searchContact" class="form-control mb-3" placeholder="Search contacts...">
                            <div id="contactListModal"></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Bulk SMS Section -->
        <div id="bulkSection" style="display:none;">
            <div class="card">
                <div class="card-header">
                    <i class="fas fa-layer-group"></i> Bulk SMS
                </div>
                <div class="card-body">
                    <ul class="nav nav-tabs" id="bulkTabs">
                        <li class="nav-item">
                            <a class="nav-link active" data-bs-toggle="tab" href="#importNumbers">Import Numbers</a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" data-bs-toggle="tab" href="#pasteNumbers">Paste Numbers</a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" data-bs-toggle="tab" href="#selectGroup">Select Group</a>
                        </li>
                    </ul>
                    
                    <div class="tab-content mt-3">
                        <div class="tab-pane active" id="importNumbers">
                            <label>Import CSV/Excel File</label>
                            <input type="file" id="bulkFile" class="form-control" accept=".csv,.xlsx">
                            <button class="btn btn-primary mt-2" onclick="previewBulkNumbers()">
                                <i class="fas fa-eye"></i> Preview
                            </button>
                        </div>
                        
                        <div class="tab-pane" id="pasteNumbers">
                            <label>Paste Numbers (one per line)</label>
                            <textarea id="pasteNumbersList" rows="6" class="form-control" 
                                placeholder="+216XXXXXXXXX&#10;+216YYYYYYYYY&#10;+216ZZZZZZZZZ"></textarea>
                        </div>
                        
                        <div class="tab-pane" id="selectGroup">
                            <label>Select Group</label>
                            <select id="bulkGroup" class="form-control">
                                <option value="">Choose group...</option>
                            </select>
                        </div>
                    </div>
                    
                    <div class="mt-3">
                        <label>Message</label>
                        <textarea id="bulkMessage" rows="4" class="form-control" placeholder="Message for all numbers"></textarea>
                        <div class="mt-2">
                            <label><input type="checkbox" id="personalizeMessage"> Personalize with {name}</label>
                        </div>
                    </div>
                    
                    <div class="mt-3">
                        <button class="btn btn-gradient" onclick="sendBulkSMS()">
                            <i class="fas fa-rocket"></i> Send Bulk SMS
                        </button>
                        <button class="btn btn-info" onclick="exportNumbers()">
                            <i class="fas fa-download"></i> Export Numbers
                        </button>
                    </div>
                    
                    <div id="bulkPreview" class="mt-3"></div>
                    <div id="bulkProgress" class="mt-3" style="display:none;">
                        <div class="progress">
                            <div id="bulkProgressBar" class="progress-bar progress-bar-gradient" role="progressbar" style="width: 0%"></div>
                        </div>
                        <div id="bulkStatus" class="mt-2"></div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Contacts Section -->
        <div id="contactsSection" style="display:none;">
            <div class="card">
                <div class="card-header">
                    <i class="fas fa-address-book"></i> Contact Management
                    <button class="btn btn-sm btn-success float-end" onclick="showAddContactModal()">
                        <i class="fas fa-plus"></i> Add Contact
                    </button>
                </div>
                <div class="card-body">
                    <input type="text" id="searchContacts" class="form-control mb-3" placeholder="Search contacts...">
                    <div class="table-responsive">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Name</th>
                                    <th>Number</th>
                                    <th>Group</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody id="contactsTable"></tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Groups Section -->
        <div id="groupsSection" style="display:none;">
            <div class="card">
                <div class="card-header">
                    <i class="fas fa-users"></i> Groups
                    <button class="btn btn-sm btn-success float-end" onclick="showAddGroupModal()">
                        <i class="fas fa-plus"></i> Create Group
                    </button>
                </div>
                <div class="card-body">
                    <div id="groupsList"></div>
                </div>
            </div>
        </div>
        
        <!-- Templates Section -->
        <div id="templatesSection" style="display:none;">
            <div class="card">
                <div class="card-header">
                    <i class="fas fa-file-alt"></i> SMS Templates
                    <button class="btn btn-sm btn-success float-end" onclick="showAddTemplateModal()">
                        <i class="fas fa-plus"></i> New Template
                    </button>
                </div>
                <div class="card-body">
                    <div id="templatesList"></div>
                </div>
            </div>
        </div>
        
        <!-- Campaigns Section -->
        <div id="campaignsSection" style="display:none;">
            <div class="card">
                <div class="card-header">
                    <i class="fas fa-bullhorn"></i> SMS Campaigns
                    <button class="btn btn-sm btn-success float-end" onclick="showCreateCampaignModal()">
                        <i class="fas fa-plus"></i> New Campaign
                    </button>
                </div>
                <div class="card-body">
                    <div id="campaignsList"></div>
                </div>
            </div>
        </div>
        
        <!-- History Section -->
        <div id="historySection" style="display:none;">
            <div class="card">
                <div class="card-header">
                    <i class="fas fa-history"></i> Message History
                </div>
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-4">
                            <input type="text" id="searchHistory" class="form-control" placeholder="Search by number...">
                        </div>
                        <div class="col-md-3">
                            <select id="filterStatus" class="form-control">
                                <option value="">All Status</option>
                                <option value="Sent">Success</option>
                                <option value="Failed">Failed</option>
                            </select>
                        </div>
                        <div class="col-md-3">
                            <input type="date" id="filterDate" class="form-control">
                        </div>
                        <div class="col-md-2">
                            <button class="btn btn-info" onclick="exportHistory()">
                                <i class="fas fa-download"></i> Export CSV
                            </button>
                        </div>
                    </div>
                    <div class="table-responsive mt-3">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>Number</th>
                                    <th>Message</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody id="historyTable"></tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Blacklist Section -->
        <div id="blacklistSection" style="display:none;">
            <div class="card">
                <div class="card-header">
                    <i class="fas fa-ban"></i> Blacklist
                </div>
                <div class="card-body">
                    <div class="input-group mb-3">
                        <input type="text" id="blacklistNumber" class="form-control" placeholder="Number to block">
                        <input type="text" id="blacklistReason" class="form-control" placeholder="Reason">
                        <button class="btn btn-danger" onclick="addToBlacklist()">
                            <i class="fas fa-ban"></i> Block Number
                        </button>
                    </div>
                    <div id="blacklistList"></div>
                </div>
            </div>
        </div>
        
        <!-- Analytics Section -->
        <div id="analyticsSection" style="display:none;">
            <div class="card">
                <div class="card-header">
                    <i class="fas fa-chart-bar"></i> Advanced Analytics
                </div>
                <div class="card-body">
                    <canvas id="analyticsChart" height="100"></canvas>
                    <div id="analyticsStats" class="mt-3"></div>
                </div>
            </div>
        </div>
        
        <!-- API Docs Section -->
        <div id="apiSection" style="display:none;">
            <div class="card">
                <div class="card-header">
                    <i class="fas fa-code"></i> API Documentation
                </div>
                <div class="card-body">
                    <h5>Authentication</h5>
                    <pre class="bg-light p-3 rounded">API Key: {{ api_key }}</pre>
                    
                    <h5 class="mt-3">Send Single SMS</h5>
                    <pre class="bg-light p-3 rounded">
GET /api/send?key={{ api_key }}&to=NUMBER&text=MESSAGE
POST /api/send
{
    "key": "{{ api_key }}",
    "number": "+216XXXXXXXX",
    "message": "Hello World"
}</pre>
                    
                    <h5 class="mt-3">Send Bulk SMS</h5>
                    <pre class="bg-light p-3 rounded">
POST /api/bulk
{
    "key": "{{ api_key }}",
    "numbers": ["+216XXXXXXXX", "+216YYYYYYYY"],
    "message": "Bulk message"
}</pre>
                    
                    <h5 class="mt-3">Get Statistics</h5>
                    <pre class="bg-light p-3 rounded">
GET /api/stats?key={{ api_key }}</pre>
                    
                    <h5 class="mt-3">Get Contacts</h5>
                    <pre class="bg-light p-3 rounded">
GET /api/contacts?key={{ api_key }}</pre>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Modals -->
    <div class="modal fade" id="addContactModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Add Contact</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <input type="text" id="newContactName" class="form-control mb-2" placeholder="Name">
                    <input type="text" id="newContactNumber" class="form-control mb-2" placeholder="Phone Number">
                    <input type="text" id="newContactGroup" class="form-control mb-2" placeholder="Group">
                    <textarea id="newContactNotes" class="form-control" placeholder="Notes"></textarea>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-primary" onclick="addContact()">Save</button>
                </div>
            </div>
        </div>
    </div>
    
    <div class="toast-notification" id="notification"></div>
    
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let smsChart = null;
        let currentBulkNumbers = [];
        
        function toggleSidebar() {
            document.getElementById('sidebar').classList.toggle('show-sidebar');
        }
        
        function showSection(section) {
            const sections = ['dashboard', 'send', 'bulk', 'contacts', 'groups', 'templates', 'campaigns', 'history', 'blacklist', 'analytics', 'api'];
            sections.forEach(s => {
                document.getElementById(s + 'Section').style.display = 'none';
            });
            document.getElementById(section + 'Section').style.display = 'block';
            
            if (section === 'dashboard') loadDashboard();
            if (section === 'contacts') loadContacts();
            if (section === 'groups') loadGroups();
            if (section === 'templates') loadTemplates();
            if (section === 'campaigns') loadCampaigns();
            if (section === 'history') loadHistory();
            if (section === 'blacklist') loadBlacklist();
            if (section === 'analytics') loadAnalytics();
        }
        
        async function loadDashboard() {
            const stats = await fetch('/api/stats').then(r => r.json());
            document.getElementById('totalSMS').innerText = stats.total;
            document.getElementById('successRate').innerText = stats.success_rate + '%';
            document.getElementById('totalContacts').innerText = stats.contacts;
            document.getElementById('todaySMS').innerText = stats.today;
            
            // Load chart
            const chartData = await fetch('/api/chart-data').then(r => r.json());
            if (smsChart) smsChart.destroy();
            const ctx = document.getElementById('smsChart').getContext('2d');
            smsChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: chartData.labels,
                    datasets: [{
                        label: 'SMS Sent',
                        data: chartData.values,
                        borderColor: '#667eea',
                        backgroundColor: 'rgba(102,126,234,0.1)'
                    }]
                }
            });
            
            // Recent activity
            const history = await fetch('/api/history').then(r => r.json());
            let html = '';
            history.history.slice(0, 5).forEach(h => {
                html += `<div class="mb-2">✅ ${h.timestamp} - ${h.number}: ${h.message.substring(0,30)}</div>`;
            });
            document.getElementById('recentActivity').innerHTML = html;
        }
        
        async function sendSingleSMS() {
            const number = document.getElementById('singleNumber').value;
            const message = document.getElementById('singleMessage').value;
            
            if (!number || !message) {
                showNotification('Fill all fields', 'error');
                return;
            }
            
            const response = await fetch('/api/send', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({number, message, key: '{{ api_key }}'})
            });
            const data = await response.json();
            
            if (data.success) {
                showNotification('SMS sent successfully!', 'success');
                document.getElementById('singleNumber').value = '';
                document.getElementById('singleMessage').value = '';
                loadDashboard();
                loadHistory();
            } else {
                showNotification('Failed: ' + data.message, 'error');
            }
        }
        
        async function sendBulkSMS() {
            let numbers = [];
            
            // Get numbers from active tab
            if (document.querySelector('#importNumbers').classList.contains('active')) {
                if (currentBulkNumbers.length === 0) {
                    showNotification('Import numbers first', 'error');
                    return;
                }
                numbers = currentBulkNumbers;
            } else if (document.querySelector('#pasteNumbers').classList.contains('active')) {
                const text = document.getElementById('pasteNumbersList').value;
                numbers = text.split('\\n').filter(n => n.trim());
            } else if (document.querySelector('#selectGroup').classList.contains('active')) {
                const groupId = document.getElementById('bulkGroup').value;
                if (!groupId) {
                    showNotification('Select a group', 'error');
                    return;
                }
                const response = await fetch(`/api/group-contacts/${groupId}`);
                const contacts = await response.json();
                numbers = contacts.map(c => c.number);
            }
            
            const message = document.getElementById('bulkMessage').value;
            if (!message) {
                showNotification('Enter message', 'error');
                return;
            }
            
            document.getElementById('bulkProgress').style.display = 'block';
            let sent = 0;
            
            for (let i = 0; i < numbers.length; i++) {
                const percent = ((i + 1) / numbers.length) * 100;
                document.getElementById('bulkProgressBar').style.width = percent + '%';
                document.getElementById('bulkStatus').innerHTML = `Sending ${i+1}/${numbers.length}...`;
                
                await fetch('/api/send', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({number: numbers[i], message, key: '{{ api_key }}'})
                });
                sent++;
                await new Promise(r => setTimeout(r, 500));
            }
            
            showNotification(`Sent ${sent}/${numbers.length} messages`, 'success');
            document.getElementById('bulkProgress').style.display = 'none';
            loadDashboard();
        }
        
        async function loadContacts() {
            const contacts = await fetch('/api/contacts').then(r => r.json());
            let html = '';
            contacts.forEach(c => {
                html += `<tr>
                    <td>${c.name}</td>
                    <td>${c.number}</td>
                    <td>${c.group_name || '-'}</td>
                    <td>
                        <button class="btn btn-sm btn-primary" onclick="sendToContact('${c.number}')">
                            <i class="fas fa-paper-plane"></i>
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="deleteContact(${c.id})">
                            <i class="fas fa-trash"></i>
                        </button>
                    </td>
                </tr>`;
            });
            document.getElementById('contactsTable').innerHTML = html;
        }
        
        async function loadGroups() {
            const groups = await fetch('/api/groups').then(r => r.json());
            let html = '';
            for (const group of groups) {
                const members = await fetch(`/api/group-contacts/${group.id}`).then(r => r.json());
                html += `
                    <div class="card mb-2">
                        <div class="card-body">
                            <h5>${group.name}</h5>
                            <p>Members: ${members.length}</p>
                            <button class="btn btn-sm btn-primary" onclick="sendToGroup(${group.id})">
                                <i class="fas fa-paper-plane"></i> Send to Group
                            </button>
                            <button class="btn btn-sm btn-danger" onclick="deleteGroup(${group.id})">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                `;
            }
            document.getElementById('groupsList').innerHTML = html || '<p>No groups yet</p>';
        }
        
        async function loadTemplates() {
            const templates = await fetch('/api/templates').then(r => r.json());
            let html = '<div class="row">';
            templates.forEach(t => {
                html += `
                    <div class="col-md-4 mb-3">
                        <div class="card">
                            <div class="card-body">
                                <h6>${t.name}</h6>
                                <p class="small">${t.content.substring(0, 100)}</p>
                                <button class="btn btn-sm btn-primary" onclick="useTemplate(${t.id})">
                                    <i class="fas fa-paste"></i> Use
                                </button>
                                <button class="btn btn-sm btn-danger" onclick="deleteTemplate(${t.id})">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            });
            html += '</div>';
            document.getElementById('templatesList').innerHTML = html || '<p>No templates yet</p>';
        }
        
        async function loadHistory() {
            const history = await fetch('/api/history').then(r => r.json());
            let html = '';
            history.history.forEach(h => {
                html += `<tr>
                    <td>${h.timestamp}</td>
                    <td>${h.number}</td>
                    <td>${h.message.substring(0, 50)}</td>
                    <td><span class="badge badge-${h.status === 'Sent' ? 'success' : 'danger'}">${h.status}</span></td>
                </tr>`;
            });
            document.getElementById('historyTable').innerHTML = html;
        }
        
        function sendToContact(number) {
            document.getElementById('singleNumber').value = number;
            showSection('send');
        }
        
        async function addContact() {
            const contact = {
                name: document.getElementById('newContactName').value,
                number: document.getElementById('newContactNumber').value,
                group: document.getElementById('newContactGroup').value,
                notes: document.getElementById('newContactNotes').value
            };
            
            await fetch('/api/contacts', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(contact)
            });
            
            bootstrap.Modal.getInstance(document.getElementById('addContactModal')).hide();
            loadContacts();
            showNotification('Contact added!', 'success');
        }
        
        function showNotification(message, type) {
            const notification = document.getElementById('notification');
            notification.innerHTML = `
                <div class="toast show" role="alert">
                    <div class="toast-header bg-${type === 'success' ? 'success' : 'danger'} text-white">
                        <strong class="me-auto">SMS Gateway</strong>
                        <button type="button" class="btn-close" data-bs-dismiss="toast"></button>
                    </div>
                    <div class="toast-body">${message}</div>
                </div>
            `;
            setTimeout(() => {
                notification.innerHTML = '';
            }, 3000);
        }
        
        // Character counter
        document.getElementById('singleMessage')?.addEventListener('input', function() {
            document.getElementById('charCount').innerText = this.value.length + ' / 160 characters';
        });
        
        // Load quick numbers
        async function loadQuickNumbers() {
            const contacts = await fetch('/api/contacts').then(r => r.json());
            const select = document.getElementById('quickNumber');
            contacts.forEach(c => {
                const option = document.createElement('option');
                option.value = c.number;
                option.text = `${c.name} (${c.number})`;
                select.appendChild(option);
            });
        }
        
        function selectQuickNumber() {
            const select = document.getElementById('quickNumber');
            document.getElementById('singleNumber').value = select.value;
        }
        
        // Initialize
        loadDashboard();
        loadQuickNumbers();
        loadGroups();
        
        // Auto refresh every 30 seconds
        setInterval(() => {
            if (document.getElementById('dashboardSection').style.display !== 'none') {
                loadDashboard();
            }
        }, 30000);
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
            return render_template_string(PRO_DASHBOARD, api_key=API_KEY)
        return '<h3>Invalid credentials!</h3><a href="/">Try again</a>'
    
    if session.get('logged_in'):
        return render_template_string(PRO_DASHBOARD, api_key=API_KEY)
    return '''
    <!DOCTYPE html>
    <html>
    <head><title>Login</title><style>
        body{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);font-family:Arial;display:flex;justify-content:center;align-items:center;height:100vh;}
        .card{background:white;padding:40px;border-radius:20px;width:350px;box-shadow:0 10px 40px rgba(0,0,0,0.2);}
        input{width:100%;padding:12px;margin:10px 0;border:2px solid #e0e0e0;border-radius:10px;}
        button{width:100%;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:12px;border:none;border-radius:10px;cursor:pointer;font-size:16px;}
        h2{text-align:center;color:#333;}
    </style></head>
    <body>
        <div class="card"><h2>🔐 SMS Ultra Pro</h2>
        <form method="POST"><input name="username" placeholder="Username" required><input type="password" name="password" placeholder="Password" required><button type="submit">Login</button></form></div>
    </body>
    </html>
    '''

@app.route('/logout')
def logout():
    session.clear()
    return '<a href="/">Logged out. Login again</a>'

# Enhanced API Endpoints
@app.route('/api/send', methods=['POST'])
def api_send():
    data = request.json
    if data.get('key') != API_KEY:
        return jsonify({"error": "Invalid API key"}), 403
    
    number, message = data.get('number'), data.get('message')
    if not number or not message:
        return jsonify({"error": "Missing fields"}), 400
    
    success, result = send_sms(number, message)
    
    conn = sqlite3.connect('sms_pro.db')
    c = conn.cursor()
    c.execute("INSERT INTO messages (number, message, status, timestamp, sender_ip) VALUES (?,?,?,?,?)",
              (number, message, 'Sent' if success else result, datetime.datetime.now(), request.remote_addr))
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
    
    results = []
    for number in numbers:
        success, result = send_sms(number, message)
        results.append({"number": number, "success": success})
    
    return jsonify({"results": results, "total": len(results)})

@app.route('/api/contacts', methods=['GET', 'POST', 'DELETE'])
def manage_contacts():
    conn = sqlite3.connect('sms_pro.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        data = request.json
        c.execute("INSERT INTO contacts (name, number, group_name, notes, created) VALUES (?,?,?,?,?)",
                  (data['name'], data['number'], data.get('group'), data.get('notes'), datetime.datetime.now()))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    
    if request.method == 'DELETE':
        contact_id = request.args.get('id')
        c.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    
    c.execute("SELECT id, name, number, group_name, notes FROM contacts ORDER BY name")
    contacts = [{"id": row[0], "name": row[1], "number": row[2], "group_name": row[3], "notes": row[4]} for row in c.fetchall()]
    conn.close()
    return jsonify(contacts)

@app.route('/api/groups', methods=['GET', 'POST'])
def manage_groups():
    conn = sqlite3.connect('sms_pro.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        data = request.json
        c.execute("INSERT INTO groups (name, description, created) VALUES (?,?,?)",
                  (data['name'], data.get('description'), datetime.datetime.now()))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    
    c.execute("SELECT id, name, description FROM groups")
    groups = [{"id": row[0], "name": row[1], "description": row[2]} for row in c.fetchall()]
    conn.close()
    return jsonify(groups)

@app.route('/api/group-contacts/<int:group_id>')
def get_group_contacts(group_id):
    conn = sqlite3.connect('sms_pro.db')
    c = conn.cursor()
    c.execute("SELECT name, number FROM contacts WHERE group_name = (SELECT name FROM groups WHERE id=?)", (group_id,))
    contacts = [{"name": row[0], "number": row[1]} for row in c.fetchall()]
    conn.close()
    return jsonify(contacts)

@app.route('/api/templates', methods=['GET', 'POST'])
def manage_templates():
    conn = sqlite3.connect('sms_pro.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        data = request.json
        c.execute("INSERT INTO templates (name, content, category, created) VALUES (?,?,?,?)",
                  (data['name'], data['content'], data.get('category'), datetime.datetime.now()))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    
    c.execute("SELECT id, name, content, category FROM templates")
    templates = [{"id": row[0], "name": row[1], "content": row[2], "category": row[3]} for row in c.fetchall()]
    conn.close()
    return jsonify(templates)

@app.route('/api/history')
def get_history():
    conn = sqlite3.connect('sms_pro.db')
    c = conn.cursor()
    c.execute("SELECT timestamp, number, message, status FROM messages ORDER BY timestamp DESC LIMIT 100")
    history = [{"timestamp": row[0], "number": row[1], "message": row[2], "status": row[3]} for row in c.fetchall()]
    conn.close()
    return jsonify({"history": history})

@app.route('/api/stats')
def get_stats():
    conn = sqlite3.connect('sms_pro.db')
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
    conn = sqlite3.connect('sms_pro.db')
    c = conn.cursor()
    c.execute("SELECT date(timestamp) as day, COUNT(*) FROM messages WHERE date(timestamp) >= date('now', '-7 days') GROUP BY day")
    data = c.fetchall()
    conn.close()
    
    labels = [row[0] for row in data]
    values = [row[1] for row in data]
    return jsonify({"labels": labels, "values": values})

if __name__ == '__main__':
    print("="*60)
    print("🚀 SMS ULTRA PRO - Advanced Gateway")
    print("="*60)
    print(f"📱 Local URL: http://localhost:8080")
    print(f"🔑 API Key: {API_KEY}")
    print(f"👤 Admin: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
    print("="*60)
    print("✨ NEW FEATURES:")
    print("  • 📊 Advanced Dashboard with Charts")
    print("  • 📇 Contact Management with Search")
    print("  • 👥 Group Messaging")
    print("  • 📝 SMS Templates")
    print("  • 📤 Bulk SMS (CSV/Excel/Paste)")
    print("  • 🚫 Blacklist System")
    print("  • 📈 Analytics & Reports")
    print("  • 🎯 Campaign Management")
    print("  • 🔄 Auto-retry on failure")
    print("  • 💾 Export to CSV")
    print("="*60)
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)


