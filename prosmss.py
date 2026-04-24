from flask import Flask, request, jsonify, render_template_string, session
from flask_cors import CORS
import subprocess, sqlite3, datetime, secrets, csv, io
from functools import wraps
import json

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
CORS(app)

# Configuration
API_KEY = "GlasswhiteUltimate2026"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

# Database setup
def init_db():
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  number TEXT, message TEXT, status TEXT, 
                  timestamp DATETIME, sender_ip TEXT)''')
    
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
    
    conn.commit()
    conn.close()

init_db()

# Send SMS function
def send_sms(number, message):
    try:
        subprocess.run(['termux-sms-send', '-n', number, message], timeout=15)
        return True, "Sent"
    except Exception as e:
        return False, str(e)

# HTML Dashboard
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SMS Ultimate Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); font-family: 'Segoe UI', sans-serif; }
        .sidebar { position: fixed; left: 0; top: 0; height: 100%; width: 250px; background: white; box-shadow: 2px 0 10px rgba(0,0,0,0.1); }
        .sidebar-header { background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 20px; text-align: center; }
        .sidebar-menu a { display: block; padding: 15px 25px; color: #333; text-decoration: none; transition: 0.3s; }
        .sidebar-menu a:hover, .sidebar-menu a.active { background: linear-gradient(135deg, #667eea, #764ba2); color: white; }
        .main-content { margin-left: 250px; padding: 20px; }
        .stat-card { background: white; border-radius: 15px; padding: 20px; margin-bottom: 20px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); text-align: center; }
        .stat-value { font-size: 32px; font-weight: bold; color: #667eea; }
        .card { border-radius: 15px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .btn-gradient { background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; }
        .btn-gradient:hover { transform: translateY(-2px); color: white; }
        @media (max-width: 768px) { .sidebar { left: -250px; } .main-content { margin-left: 0; } .show-sidebar { left: 0; } }
        .number-item { cursor: pointer; padding: 10px; border-bottom: 1px solid #eee; }
        .number-item:hover { background: #f0f0f0; }
    </style>
</head>
<body>
    <div class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <h4><i class="fas fa-sms"></i> SMS Pro</h4>
        </div>
        <div class="sidebar-menu">
            <a href="#" onclick="showSection('dashboard')" class="active"><i class="fas fa-chart-line"></i> Dashboard</a>
            <a href="#" onclick="showSection('send')"><i class="fas fa-paper-plane"></i> Send SMS</a>
            <a href="#" onclick="showSection('bulk')"><i class="fas fa-layer-group"></i> Bulk SMS</a>
            <a href="#" onclick="showSection('contacts')"><i class="fas fa-address-book"></i> Contacts</a>
            <a href="#" onclick="showSection('groups')"><i class="fas fa-users"></i> Groups</a>
            <a href="#" onclick="showSection('templates')"><i class="fas fa-file-alt"></i> Templates</a>
            <a href="#" onclick="showSection('history')"><i class="fas fa-history"></i> History</a>
            <a href="#" onclick="showSection('blacklist')"><i class="fas fa-ban"></i> Blacklist</a>
            <a href="#" onclick="showSection('api')"><i class="fas fa-code"></i> API</a>
        </div>
    </div>
    
    <div class="main-content">
        <button class="btn btn-dark mb-3 d-md-none" onclick="toggleSidebar()"><i class="fas fa-bars"></i> Menu</button>
        
        <div id="dashboardSection">
            <div class="row">
                <div class="col-md-3"><div class="stat-card"><i class="fas fa-envelope fa-2x"></i><div class="stat-value" id="totalSMS">0</div><div>Total SMS</div></div></div>
                <div class="col-md-3"><div class="stat-card"><i class="fas fa-check-circle fa-2x"></i><div class="stat-value" id="successRate">0%</div><div>Success Rate</div></div></div>
                <div class="col-md-3"><div class="stat-card"><i class="fas fa-users fa-2x"></i><div class="stat-value" id="totalContacts">0</div><div>Contacts</div></div></div>
                <div class="col-md-3"><div class="stat-card"><i class="fas fa-clock fa-2x"></i><div class="stat-value" id="todaySMS">0</div><div>Today</div></div></div>
            </div>
            <div class="card"><div class="card-body"><canvas id="smsChart"></canvas></div></div>
        </div>
        
        <div id="sendSection" style="display:none;">
            <div class="card">
                <div class="card-header"><b><i class="fas fa-paper-plane"></i> Send SMS</b></div>
                <div class="card-body">
                    <label>Phone Number</label>
                    <div class="input-group">
                        <input type="text" id="singleNumber" class="form-control" placeholder="+216XXXXXXXX">
                        <button class="btn btn-secondary" onclick="showContactList()"><i class="fas fa-list"></i> Contacts</button>
                    </div>
                    <label class="mt-2">Message</label>
                    <textarea id="singleMessage" rows="4" class="form-control"></textarea>
                    <small id="charCount" class="text-muted">0/160</small>
                    <button class="btn btn-gradient mt-3" onclick="sendSMS()"><i class="fas fa-paper-plane"></i> Send</button>
                    <div id="sendResult" class="mt-3"></div>
                </div>
            </div>
        </div>
        
        <div id="bulkSection" style="display:none;">
            <div class="card">
                <div class="card-header"><b><i class="fas fa-layer-group"></i> Bulk SMS</b></div>
                <div class="card-body">
                    <label>Paste Numbers (one per line)</label>
                    <textarea id="bulkNumbers" rows="5" class="form-control" placeholder="+216XXXXXXXXX&#10;+216YYYYYYYYY"></textarea>
                    <label class="mt-2">Message</label>
                    <textarea id="bulkMessage" rows="3" class="form-control"></textarea>
                    <button class="btn btn-gradient mt-3" onclick="sendBulkSMS()"><i class="fas fa-rocket"></i> Send to All</button>
                    <div id="bulkProgress" class="mt-3" style="display:none;">
                        <div class="progress"><div id="bulkBar" class="progress-bar bg-success" style="width:0%"></div></div>
                        <div id="bulkStatus" class="mt-2"></div>
                    </div>
                </div>
            </div>
        </div>
        
        <div id="contactsSection" style="display:none;">
            <div class="card">
                <div class="card-header"><b><i class="fas fa-address-book"></i> Contacts</b>
                    <button class="btn btn-sm btn-success float-end" onclick="showAddContact()"><i class="fas fa-plus"></i> Add</button>
                </div>
                <div class="card-body">
                    <input type="text" id="searchContact" class="form-control mb-3" placeholder="Search...">
                    <div id="contactsList"></div>
                </div>
            </div>
        </div>
        
        <div id="groupsSection" style="display:none;">
            <div class="card">
                <div class="card-header"><b><i class="fas fa-users"></i> Groups</b>
                    <button class="btn btn-sm btn-success float-end" onclick="showAddGroup()"><i class="fas fa-plus"></i> Create</button>
                </div>
                <div class="card-body"><div id="groupsList"></div></div>
            </div>
        </div>
        
        <div id="templatesSection" style="display:none;">
            <div class="card">
                <div class="card-header"><b><i class="fas fa-file-alt"></i> Templates</b>
                    <button class="btn btn-sm btn-success float-end" onclick="showAddTemplate()"><i class="fas fa-plus"></i> Add</button>
                </div>
                <div class="card-body"><div id="templatesList"></div></div>
            </div>
        </div>
        
        <div id="historySection" style="display:none;">
            <div class="card">
                <div class="card-header"><b><i class="fas fa-history"></i> Message History</b></div>
                <div class="card-body">
                    <div class="table-responsive"><table class="table" id="historyTable"></table></div>
                </div>
            </div>
        </div>
        
        <div id="blacklistSection" style="display:none;">
            <div class="card">
                <div class="card-header"><b><i class="fas fa-ban"></i> Blacklist</b></div>
                <div class="card-body">
                    <div class="input-group mb-3">
                        <input type="text" id="blockNumber" class="form-control" placeholder="Number to block">
                        <button class="btn btn-danger" onclick="addToBlacklist()">Block</button>
                    </div>
                    <div id="blacklistList"></div>
                </div>
            </div>
        </div>
        
        <div id="apiSection" style="display:none;">
            <div class="card">
                <div class="card-header"><b><i class="fas fa-code"></i> API Documentation</b></div>
                <div class="card-body">
                    <h6>Send SMS:</h6>
                    <pre class="bg-light p-2 rounded">GET /api/send?key={{ api_key }}&to=NUMBER&text=MESSAGE</pre>
                    <h6>API Key:</h6>
                    <code>{{ api_key }}</code>
                </div>
            </div>
        </div>
    </div>
    
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
        
        function toggleSidebar() { document.getElementById('sidebar').classList.toggle('show-sidebar'); }
        
        function showSection(section) {
            ['dashboard','send','bulk','contacts','groups','templates','history','blacklist','api'].forEach(s => {
                document.getElementById(s+'Section').style.display = 'none';
            });
            document.getElementById(section+'Section').style.display = 'block';
            if(section=='dashboard') loadDashboard();
            if(section=='contacts') loadContacts();
            if(section=='groups') loadGroups();
            if(section=='templates') loadTemplates();
            if(section=='history') loadHistory();
            if(section=='blacklist') loadBlacklist();
        }
        
        async function loadDashboard() {
            let stats = await fetch('/api/stats').then(r=>r.json());
            document.getElementById('totalSMS').innerText = stats.total;
            document.getElementById('successRate').innerText = stats.success_rate+'%';
            document.getElementById('totalContacts').innerText = stats.contacts;
            document.getElementById('todaySMS').innerText = stats.today;
            
            let chartData = await fetch('/api/chart-data').then(r=>r.json());
            if(chart) chart.destroy();
            chart = new Chart(document.getElementById('smsChart'), {
                type: 'line',
                data: { labels: chartData.labels, datasets: [{ label: 'SMS', data: chartData.values, borderColor: '#667eea', fill: false }] }
            });
        }
        
        async function sendSMS() {
            let number = document.getElementById('singleNumber').value;
            let message = document.getElementById('singleMessage').value;
            if(!number||!message){ alert('Fill all fields'); return; }
            let res = await fetch('/api/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({number,message,key:'{{ api_key }}'})});
            let data = await res.json();
            document.getElementById('sendResult').innerHTML = data.success ? '<div class="alert alert-success">✅ Sent!</div>' : '<div class="alert alert-danger">❌ Failed</div>';
            if(data.success){ document.getElementById('singleNumber').value=''; document.getElementById('singleMessage').value=''; loadDashboard(); loadHistory(); }
        }
        
        async function sendBulkSMS() {
            let numbersText = document.getElementById('bulkNumbers').value;
            let message = document.getElementById('bulkMessage').value;
            let numbers = numbersText.split('\\n').filter(n=>n.trim());
            if(numbers.length==0||!message){ alert('Enter numbers and message'); return; }
            document.getElementById('bulkProgress').style.display='block';
            let sent=0;
            for(let i=0;i<numbers.length;i++){
                let percent = ((i+1)/numbers.length)*100;
                document.getElementById('bulkBar').style.width=percent+'%';
                document.getElementById('bulkStatus').innerHTML=`Sending ${i+1}/${numbers.length}`;
                await fetch('/api/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({number:numbers[i],message,key:'{{ api_key }}'})});
                sent++;
                await new Promise(r=>setTimeout(r,500));
            }
            document.getElementById('bulkProgress').style.display='none';
            alert(`Sent ${sent}/${numbers.length} messages`);
            loadDashboard();
        }
        
        async function loadContacts() {
            let contacts = await fetch('/api/contacts').then(r=>r.json());
            let html='<div class="list-group">';
            contacts.forEach(c=>{ html+=`<div class="list-group-item"><b>${c.name}</b> - ${c.number}<br><button class="btn btn-sm btn-primary mt-1" onclick="selectContact('${c.number}')">Send</button> <button class="btn btn-sm btn-danger mt-1" onclick="deleteContact(${c.id})">Delete</button></div>`; });
            html+='</div>';
            document.getElementById('contactsList').innerHTML=html||'<p>No contacts</p>';
        }
        
        async function loadGroups() {
            let groups = await fetch('/api/groups').then(r=>r.json());
            let html='';
            for(let g of groups){
                let members = await fetch(`/api/group-contacts/${g.id}`).then(r=>r.json());
                html+=`<div class="card mb-2"><div class="card-body"><b>${g.name}</b> (${members.length} members)<br><button class="btn btn-sm btn-primary mt-1" onclick="sendToGroup(${g.id})">Send to Group</button></div></div>`;
            }
            document.getElementById('groupsList').innerHTML=html||'<p>No groups</p>';
        }
        
        async function loadTemplates() {
            let templates = await fetch('/api/templates').then(r=>r.json());
            let html='<div class="row">';
            templates.forEach(t=>{ html+=`<div class="col-md-4 mb-2"><div class="card"><div class="card-body"><b>${t.name}</b><p class="small">${t.content.substring(0,50)}</p><button class="btn btn-sm btn-primary" onclick="useTemplate('${t.content}')">Use</button></div></div></div>`; });
            html+='</div>';
            document.getElementById('templatesList').innerHTML=html||'<p>No templates</p>';
        }
        
        async function loadHistory() {
            let history = await fetch('/api/history').then(r=>r.json());
            let html='<tr><th>Time</th><th>Number</th><th>Message</th><th>Status</th></tr>';
            history.history.forEach(h=>{ html+=`<tr><td>${h.timestamp}</td><td>${h.number}</td><td>${h.message.substring(0,50)}</td><td>${h.status}</td></tr>`; });
            document.getElementById('historyTable').innerHTML=html;
        }
        
        async function loadBlacklist() {
            let blacklist = await fetch('/api/blacklist').then(r=>r.json());
            let html='<div class="list-group">';
            blacklist.forEach(b=>{ html+=`<div class="list-group-item"><b>${b.number}</b> - ${b.reason}<button class="btn btn-sm btn-danger float-end" onclick="removeFromBlacklist(${b.id})">Remove</button></div>`; });
            html+='</div>';
            document.getElementById('blacklistList').innerHTML=html||'<p>No blocked numbers</p>';
        }
        
        function selectContact(number){ document.getElementById('singleNumber').value=number; showSection('send'); bootstrap.Modal.getInstance(document.getElementById('contactListModal')).hide(); }
        function showAddContact(){ new bootstrap.Modal(document.getElementById('contactModal')).show(); }
        function showAddGroup(){ new bootstrap.Modal(document.getElementById('groupModal')).show(); }
        function showAddTemplate(){ new bootstrap.Modal(document.getElementById('templateModal')).show(); }
        function showContactList(){ loadContactsForSelector(); new bootstrap.Modal(document.getElementById('contactListModal')).show(); }
        
        async function loadContactsForSelector(){
            let contacts = await fetch('/api/contacts').then(r=>r.json());
            let html='';
            contacts.forEach(c=>{ html+=`<div class="number-item" onclick="selectContact('${c.number}')"><b>${c.name}</b><br>${c.number}</div>`; });
            document.getElementById('contactSelector').innerHTML=html;
        }
        
        async function addContact(){
            let contact={name:document.getElementById('contactName').value,number:document.getElementById('contactNumber').value,group:document.getElementById('contactGroup').value};
            await fetch('/api/contacts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(contact)});
            bootstrap.Modal.getInstance(document.getElementById('contactModal')).hide();
            loadContacts();
        }
        
        async function createGroup(){
            let name=document.getElementById('groupName').value;
            await fetch('/api/groups',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});
            bootstrap.Modal.getInstance(document.getElementById('groupModal')).hide();
            loadGroups();
        }
        
        async function addTemplate(){
            let template={name:document.getElementById('templateName').value,content:document.getElementById('templateContent').value};
            await fetch('/api/templates',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(template)});
            bootstrap.Modal.getInstance(document.getElementById('templateModal')).hide();
            loadTemplates();
        }
        
        function useTemplate(content){ document.getElementById('singleMessage').value=content; showSection('send'); }
        async function deleteContact(id){ await fetch(`/api/contacts?id=${id}`,{method:'DELETE'}); loadContacts(); }
        async function addToBlacklist(){ let number=document.getElementById('blockNumber').value; await fetch('/api/blacklist',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({number})}); loadBlacklist(); document.getElementById('blockNumber').value=''; }
        async function removeFromBlacklist(id){ await fetch(`/api/blacklist?id=${id}`,{method:'DELETE'}); loadBlacklist(); }
        async function sendToGroup(groupId){ let message=prompt('Enter message for group:'); if(message){ let res=await fetch('/api/send-group',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({groupId,message,key:'{{ api_key }}'})}); let data=await res.json(); alert(data.message); } }
        
        document.getElementById('singleMessage')?.addEventListener('input',function(){ document.getElementById('charCount').innerText=this.value.length+'/160'; });
        loadDashboard();
        loadQuickNumbers();
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
    if not number or not message:
        return jsonify({"error": "Missing fields"}), 400
    success, result = send_sms(number, message)
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    c.execute("INSERT INTO messages (number, message, status, timestamp, sender_ip) VALUES (?,?,?,?,?)",
              (number, message, 'Sent' if success else result, datetime.datetime.now(), request.remote_addr))
    conn.commit()
    conn.close()
    return jsonify({"success": success, "message": result})

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

@app.route('/api/groups', methods=['GET', 'POST'])
def manage_groups():
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    if request.method == 'POST':
        data = request.json
        c.execute("INSERT INTO groups (name, created) VALUES (?,?)", (data['name'], datetime.datetime.now()))
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

@app.route('/api/templates', methods=['GET', 'POST'])
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
    c.execute("SELECT id, name, content FROM templates")
    templates = [{"id": row[0], "name": row[1], "content": row[2]} for row in c.fetchall()]
    conn.close()
    return jsonify(templates)

@app.route('/api/history')
def get_history():
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    c.execute("SELECT timestamp, number, message, status FROM messages ORDER BY timestamp DESC LIMIT 100")
    history = [{"timestamp": row[0], "number": row[1], "message": row[2], "status": row[3]} for row in c.fetchall()]
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

@app.route('/api/blacklist', methods=['GET', 'POST', 'DELETE'])
def manage_blacklist():
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    if request.method == 'POST':
        data = request.json
        try:
            c.execute("INSERT INTO blacklist (number, reason, created) VALUES (?,?,?)",
                      (data['number'], data.get('reason', 'Manual block'), datetime.datetime.now()))
            conn.commit()
        except:
            pass
        conn.close()
        return jsonify({"success": True})
    if request.method == 'DELETE':
        blacklist_id = request.args.get('id')
        c.execute("DELETE FROM blacklist WHERE id = ?", (blacklist_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    c.execute("SELECT id, number, reason FROM blacklist")
    blacklist = [{"id": row[0], "number": row[1], "reason": row[2]} for row in c.fetchall()]
    conn.close()
    return jsonify(blacklist)

@app.route('/api/send-group', methods=['POST'])
def send_to_group():
    data = request.json
    if data.get('key') != API_KEY:
        return jsonify({"error": "Invalid API key"}), 403
    conn = sqlite3.connect('sms_ultimate.db')
    c = conn.cursor()
    c.execute("SELECT number FROM contacts WHERE group_name = (SELECT name FROM groups WHERE id=?)", (data.get('groupId'),))
    contacts = c.fetchall()
    conn.close()
    success_count = 0
    for contact in contacts:
        success, _ = send_sms(contact[0], data.get('message'))
        if success:
            success_count += 1
    return jsonify({"success": True, "message": f"Sent to {success_count}/{len(contacts)} contacts"})

if __name__ == '__main__':
    print("="*60)
    print("🚀 SMS ULTRA PRO - Fixed Version")
    print("="*60)
    print(f"📱 Local URL: http://localhost:8080")
    print(f"🔑 API Key: {API_KEY}")
    print(f"👤 Admin: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
    print("="*60)
    print("✨ FEATURES:")
    print("  • Dashboard with Charts")
    print("  • Contact Management")
    print("  • Groups & Bulk SMS")
    print("  • Templates")
    print("  • Message History")
    print("  • Blacklist System")
    print("  • REST API")
    print("="*60)
    app.run(host='0.0.0.0', port=8080, debug=False)
EOF
