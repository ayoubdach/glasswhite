from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from flask_cors import CORS
import subprocess, sqlite3, datetime, secrets, hashlib, random, string
import re

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
CORS(app)

# Configuration
API_KEY = "GlasswhiteUltimate2026"

# Database setup
def init_db():
    conn = sqlite3.connect('sms_simple_login.db')
    c = conn.cursor()
    
    # Messages table
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT,
                  number TEXT, message TEXT, status TEXT, 
                  timestamp DATETIME, sender_ip TEXT)''')
    
    # Contacts table
    c.execute('''CREATE TABLE IF NOT EXISTS contacts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT,
                  name TEXT, number TEXT, group_name TEXT, 
                  created DATETIME)''')
    
    # Users table with generated password
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password_hash TEXT,
                  created DATETIME,
                  last_login DATETIME)''')
    
    # Create default users if not exists
    default_users = ['admin', 'user1', 'user2', 'user3', 'user4', 'user5']
    for user in default_users:
        c.execute("SELECT * FROM users WHERE username = ?", (user,))
        if not c.fetchone():
            # Generate random password for new users
            generated_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            password_hash = hashlib.sha256(generated_password.encode()).hexdigest()
            c.execute("INSERT INTO users (username, password_hash, created) VALUES (?,?,?)",
                      (user, password_hash, datetime.datetime.now()))
            print(f"📝 {user} generated password: {generated_password}")
    
    conn.commit()
    conn.close()

init_db()

# Send SMS function
def send_sms_reliable(number, message, retry_count=3):
    number = re.sub(r'\s+', '', number)
    if not number.startswith('+'):
        number = '+' + number
    
    for attempt in range(retry_count):
        try:
            result = subprocess.run(
                ['termux-sms-send', '-n', number, message],
                timeout=30,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                time.sleep(2)
                return True, "Sent successfully"
            else:
                if attempt < retry_count - 1:
                    time.sleep(2)
                    continue
                return False, f"Failed: {result.stderr}"
        except Exception as e:
            if attempt < retry_count - 1:
                time.sleep(2)
                continue
            return False, str(e)
    
    return False, "Unknown error"

# HTML Templates
HOME_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <title>SMS Gateway - Choose User</title>
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
        .container {
            max-width: 500px;
            width: 100%;
        }
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
            text-align: center;
        }
        .user-btn:hover {
            transform: translateY(-3px);
        }
        .admin-btn {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }
        .footer {
            margin-top: 20px;
            color: #999;
            font-size: 12px;
        }
        .info {
            background: #d4edda;
            color: #155724;
            padding: 10px;
            border-radius: 10px;
            margin-top: 20px;
            font-size: 12px;
        }
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
            
            <div class="info">
                💡 Each user has a generated password. Click your name to see it.
            </div>
            
            <div class="footer">
                Secure SMS Gateway
            </div>
        </div>
    </div>
    
    <script>
        function selectUser(username) {
            window.location.href = '/show-password/' + username;
        }
    </script>
</body>
</html>
'''

SHOW_PASSWORD_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Your Password - {{ username }}</title>
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
        .card {
            background: white;
            border-radius: 20px;
            padding: 40px;
            width: 100%;
            max-width: 450px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
        }
        h2 { color: #333; margin-bottom: 10px; }
        .subtitle { color: #666; margin-bottom: 30px; }
        .password-box {
            background: #f0f0f0;
            padding: 20px;
            border-radius: 15px;
            margin: 20px 0;
            border: 2px dashed #667eea;
        }
        .password {
            font-size: 28px;
            font-weight: bold;
            font-family: monospace;
            letter-spacing: 2px;
            color: #667eea;
            word-break: break-all;
        }
        .copy-btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 25px;
            border-radius: 10px;
            font-size: 16px;
            cursor: pointer;
            margin: 10px;
        }
        .copy-btn:hover {
            transform: scale(1.02);
        }
        .login-btn {
            background: #28a745;
            color: white;
            border: none;
            padding: 12px 25px;
            border-radius: 10px;
            font-size: 16px;
            cursor: pointer;
            margin: 10px;
        }
        .warning {
            background: #fff3cd;
            color: #856404;
            padding: 10px;
            border-radius: 10px;
            margin: 15px 0;
            font-size: 12px;
        }
        .back-link {
            margin-top: 20px;
        }
        .back-link a {
            color: #667eea;
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="card">
        <h2>🔐 Your Password</h2>
        <p class="subtitle">Account: <strong>{{ username }}</strong></p>
        
        <div class="password-box">
            <div class="password" id="password">{{ password }}</div>
        </div>
        
        <button class="copy-btn" onclick="copyPassword()">📋 Copy Password</button>
        <button class="login-btn" onclick="goToLogin()">🔓 Go to Login</button>
        
        <div class="warning">
            ⚠️ Save this password! You will need it to login.<br>
            You can copy it now and save it somewhere safe.
        </div>
        
        <div class="back-link">
            <a href="/">← Back to user selection</a>
        </div>
    </div>
    
    <script>
        function copyPassword() {
            const password = document.getElementById('password').innerText;
            navigator.clipboard.writeText(password);
            alert('✅ Password copied! Now click "Go to Login"');
        }
        
        function goToLogin() {
            window.location.href = '/login/{{ username }}';
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
        .card {
            background: white;
            border-radius: 20px;
            padding: 40px;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
        }
        h2 { color: #333; margin-bottom: 10px; }
        .subtitle { color: #666; margin-bottom: 30px; }
        input {
            width: 100%;
            padding: 15px;
            margin: 10px 0;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 16px;
            text-align: center;
            font-family: monospace;
            letter-spacing: 2px;
        }
        input:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            width: 100%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            cursor: pointer;
            margin-top: 10px;
        }
        button:hover {
            transform: translateY(-2px);
        }
        .error {
            background: #f8d7da;
            color: #721c24;
            padding: 10px;
            border-radius: 10px;
            margin: 10px 0;
        }
        .back-link {
            margin-top: 20px;
        }
        .back-link a {
            color: #667eea;
            text-decoration: none;
        }
        .forgot {
            margin-top: 15px;
            font-size: 12px;
        }
        .forgot a {
            color: #999;
        }
    </style>
</head>
<body>
    <div class="card">
        <h2>🔐 Login</h2>
        <p class="subtitle">Account: <strong>{{ username }}</strong></p>
        
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        
        <form method="POST">
            <input type="password" name="password" placeholder="Enter your password" required autocomplete="off">
            <button type="submit">Login</button>
        </form>
        
        <div class="forgot">
            <a href="/show-password/{{ username }}">Forgot password? Show it again</a>
        </div>
        
        <div class="back-link">
            <a href="/">← Choose different user</a>
        </div>
    </div>
</body>
</html>
'''

DASHBOARD_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <title>SMS Gateway - {{ username }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); font-family: 'Segoe UI', sans-serif; padding: 20px; }
        .container { max-width: 1000px; margin: 0 auto; }
        .card { border-radius: 15px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); margin-bottom: 20px; border: none; }
        .card-header { background: white; border-bottom: 2px solid #f0f0f0; font-weight: bold; }
        .btn-gradient { background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; }
        .btn-gradient:hover { transform: translateY(-2px); color: white; }
        .stat-card { background: white; border-radius: 15px; padding: 20px; text-align: center; margin-bottom: 20px; }
        .stat-value { font-size: 32px; font-weight: bold; color: #667eea; }
        .user-badge { background: white; padding: 5px 15px; border-radius: 20px; display: inline-block; }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="card">
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <h2><i class="fas fa-sms"></i> SMS Gateway</h2>
                        <p>Welcome, <strong>{{ username }}</strong>!</p>
                    </div>
                    <div class="col-md-6 text-end">
                        <span class="user-badge"><i class="fas fa-user"></i> {{ username }}</span>
                        <a href="/logout" class="btn btn-danger btn-sm ms-2"><i class="fas fa-sign-out-alt"></i> Logout</a>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Stats -->
        <div class="row">
            <div class="col-md-4"><div class="stat-card"><i class="fas fa-envelope fa-2x"></i><div class="stat-value" id="totalSMS">0</div><div>My Messages</div></div></div>
            <div class="col-md-4"><div class="stat-card"><i class="fas fa-check-circle fa-2x"></i><div class="stat-value" id="successRate">0%</div><div>Success Rate</div></div></div>
            <div class="col-md-4"><div class="stat-card"><i class="fas fa-address-book fa-2x"></i><div class="stat-value" id="myContacts">0</div><div>My Contacts</div></div></div>
        </div>
        
        <!-- Send SMS -->
        <div class="card">
            <div class="card-header"><i class="fas fa-paper-plane"></i> Send SMS</div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-8">
                        <label>Phone Number</label>
                        <div class="input-group">
                            <input type="text" id="number" class="form-control" placeholder="+216XXXXXXXX">
                            <button class="btn btn-secondary" onclick="showContacts()"><i class="fas fa-list"></i> My Contacts</button>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <label>Quick Select</label>
                        <select id="quickContact" class="form-control" onchange="selectQuickContact()">
                            <option value="">From my contacts...</option>
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
        
        <!-- My Contacts -->
        <div class="card">
            <div class="card-header">
                <i class="fas fa-address-book"></i> My Contacts
                <button class="btn btn-sm btn-success float-end" onclick="showAddContact()"><i class="fas fa-plus"></i> Add Contact</button>
            </div>
            <div class="card-body">
                <input type="text" id="searchContact" class="form-control mb-3" placeholder="Search contacts..." onkeyup="searchContacts()">
                <div id="contactsList" class="list-group"></div>
            </div>
        </div>
        
        <!-- History -->
        <div class="card">
            <div class="card-header"><i class="fas fa-history"></i> My History</div>
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table">
                        <thead><tr><th>Time</th><th>Number</th><th>Message</th><th>Status</th></tr></thead>
                        <tbody id="historyTable"></tbody>
                    </table>
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
                    <input type="text" id="contactNumber" class="form-control mb-2" placeholder="Phone Number (+216XXXXXXXX)">
                    <input type="text" id="contactGroup" class="form-control" placeholder="Group (optional)">
                </div>
                <div class="modal-footer"><button class="btn btn-primary" onclick="addContact()">Save</button></div>
            </div>
        </div>
    </div>
    
    <!-- Contacts List Modal -->
    <div class="modal fade" id="contactsModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header"><h5>My Contacts</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
                <div class="modal-body" id="contactsModalList"></div>
            </div>
        </div>
    </div>
    
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        async function sendSMS() {
            let number = document.getElementById('number').value;
            let message = document.getElementById('message').value;
            
            if(!number || !message) {
                alert('Fill all fields');
                return;
            }
            
            let res = await fetch('/api/send', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({number, message, key: '{{ api_key }}'})
            });
            let data = await res.json();
            
            document.getElementById('result').innerHTML = data.success ? 
                '<div class="alert alert-success">✅ Sent!</div>' : 
                '<div class="alert alert-danger">❌ Failed</div>';
            
            if(data.success) {
                document.getElementById('number').value = '';
                document.getElementById('message').value = '';
                loadStats();
                loadHistory();
            }
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
            let html = '';
            let selectHtml = '<option value="">Select contact...</option>';
            
            contacts.forEach(c => {
                html += `<div class="list-group-item">
                    <div class="d-flex justify-content-between">
                        <div><strong>${c.name}</strong><br><small>${c.number}</small><br><small class="text-muted">${c.group_name || ''}</small></div>
                        <div><button class="btn btn-sm btn-primary" onclick="useNumber('${c.number}')">Send</button></div>
                    </div>
                </div>`;
                selectHtml += `<option value="${c.number}">${c.name} - ${c.number}</option>`;
            });
            
            document.getElementById('contactsList').innerHTML = html || '<p>No contacts yet</p>';
            document.getElementById('quickContact').innerHTML = selectHtml;
        }
        
        async function loadHistory() {
            let res = await fetch('/api/history');
            let data = await res.json();
            let html = '';
            data.history.forEach(h => {
                html += `<tr><td>${h.timestamp}</td><td>${h.number}</td><td>${h.message.substring(0,50)}</td><td>${h.status}</td></tr>`;
            });
            document.getElementById('historyTable').innerHTML = html;
        }
        
        function searchContacts() {
            let term = document.getElementById('searchContact').value.toLowerCase();
            let items = document.querySelectorAll('#contactsList .list-group-item');
            items.forEach(item => {
                let text = item.innerText.toLowerCase();
                item.style.display = text.includes(term) ? '' : 'none';
            });
        }
        
        function useNumber(number) {
            document.getElementById('number').value = number;
            bootstrap.Modal.getInstance(document.getElementById('contactsModal')).hide();
        }
        
        function selectQuickContact() {
            let select = document.getElementById('quickContact');
            document.getElementById('number').value = select.value;
        }
        
        function showAddContact() {
            new bootstrap.Modal(document.getElementById('contactModal')).show();
        }
        
        function showContacts() {
            let contacts = document.querySelectorAll('#contactsList .list-group-item');
            let html = '<div class="list-group">';
            contacts.forEach(c => {
                html += c.outerHTML;
            });
            html += '</div>';
            document.getElementById('contactsModalList').innerHTML = html;
            new bootstrap.Modal(document.getElementById('contactsModal')).show();
        }
        
        async function addContact() {
            let contact = {
                name: document.getElementById('contactName').value,
                number: document.getElementById('contactNumber').value,
                group: document.getElementById('contactGroup').value
            };
            await fetch('/api/contacts', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(contact)
            });
            bootstrap.Modal.getInstance(document.getElementById('contactModal')).hide();
            loadContacts();
            loadStats();
            document.getElementById('contactName').value = '';
            document.getElementById('contactNumber').value = '';
            document.getElementById('contactGroup').value = '';
        }
        
        document.getElementById('message').addEventListener('input', function() {
            document.getElementById('charCount').innerText = this.value.length + '/160';
        });
        
        loadStats();
        loadContacts();
        loadHistory();
    </script>
</body>
</html>
'''

# Routes
@app.route('/')
def home():
    return HOME_PAGE

@app.route('/show-password/<username>')
def show_password(username):
    conn = sqlite3.connect('sms_simple_login.db')
    c = conn.cursor()
    
    # Get or create user
    c.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    
    if not user:
        # Generate new password
        generated_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        password_hash = hashlib.sha256(generated_password.encode()).hexdigest()
        c.execute("INSERT INTO users (username, password_hash, created) VALUES (?,?,?)",
                  (username, password_hash, datetime.datetime.now()))
        conn.commit()
    else:
        # We need to show the password - but we only have hash!
        # So we need to store password in a separate table or regenerate
        # Let's regenerate a new password for security
        generated_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        password_hash = hashlib.sha256(generated_password.encode()).hexdigest()
        c.execute("UPDATE users SET password_hash = ? WHERE username = ?", (password_hash, username))
        conn.commit()
    
    conn.close()
    return render_template_string(SHOW_PASSWORD_PAGE, username=username, password=generated_password)

@app.route('/login/<username>', methods=['GET', 'POST'])
def login_user(username):
    if request.method == 'POST':
        password = request.form.get('password')
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        conn = sqlite3.connect('sms_simple_login.db')
        c = conn.cursor()
        c.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()
        
        if user and user[0] == password_hash:
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template_string(LOGIN_PAGE, username=username, error="❌ Invalid password")
    
    return render_template_string(LOGIN_PAGE, username=username, error=None)

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('home'))
    return render_template_string(DASHBOARD_PAGE, username=session['username'], api_key=API_KEY)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# API Routes
@app.route('/api/send', methods=['POST'])
def api_send():
    if 'username' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.json
    if data.get('key') != API_KEY:
        return jsonify({"error": "Invalid API key"}), 403
    
    number = data.get('number')
    message = data.get('message')
    
    if not number or not message:
        return jsonify({"error": "Missing fields"}), 400
    
    success, result = send_sms_reliable(number, message)
    
    conn = sqlite3.connect('sms_simple_login.db')
    c = conn.cursor()
    c.execute("INSERT INTO messages (username, number, message, status, timestamp, sender_ip) VALUES (?,?,?,?,?,?)",
              (session['username'], number, message, 'Sent' if success else 'Failed', datetime.datetime.now(), request.remote_addr))
    conn.commit()
    conn.close()
    
    return jsonify({"success": success, "message": result})

@app.route('/api/my-stats')
def my_stats():
    if 'username' not in session:
        return jsonify({}), 401
    
    conn = sqlite3.connect('sms_simple_login.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages WHERE username = ?", (session['username'],))
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM messages WHERE username = ? AND status = 'Sent'", (session['username'],))
    success = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM contacts WHERE username = ?", (session['username'],))
    contacts = c.fetchone()[0]
    
    success_rate = round((success / total * 100), 1) if total > 0 else 0
    conn.close()
    return jsonify({"total": total, "success_rate": success_rate, "contacts": contacts})

@app.route('/api/contacts', methods=['GET', 'POST'])
def manage_contacts():
    if 'username' not in session:
        return jsonify([]), 401
    
    conn = sqlite3.connect('sms_simple_login.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        data = request.json
        c.execute("INSERT INTO contacts (username, name, number, group_name, created) VALUES (?,?,?,?,?)",
                  (session['username'], data['name'], data['number'], data.get('group'), datetime.datetime.now()))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    
    c.execute("SELECT id, name, number, group_name FROM contacts WHERE username = ? ORDER BY name", (session['username'],))
    contacts = [{"id": row[0], "name": row[1], "number": row[2], "group_name": row[3]} for row in c.fetchall()]
    conn.close()
    return jsonify(contacts)

@app.route('/api/history')
def get_history():
    if 'username' not in session:
        return jsonify({"history": []}), 401
    
    conn = sqlite3.connect('sms_simple_login.db')
    c = conn.cursor()
    c.execute("SELECT timestamp, number, message, status FROM messages WHERE username = ? ORDER BY timestamp DESC LIMIT 50", (session['username'],))
    history = [{"timestamp": row[0], "number": row[1], "message": row[2], "status": row[3]} for row in c.fetchall()]
    conn.close()
    return jsonify({"history": history})

if __name__ == '__main__':
    print("="*60)
    print("🔐 SMS GATEWAY - Simple Login System")
    print("="*60)
    print(f"📱 Local URL: http://localhost:8080")
    print("="*60)
    print("👥 HOW IT WORKS:")
    print("   1. Click on your username (admin, user1-5)")
    print("   2. Copy the generated password")
    print("   3. Click 'Go to Login'")
    print("   4. Paste the password and login")
    print("="*60)
    print("💡 Passwords are generated and shown only ONCE per view")
    print("   If you forgot, click 'Show it again' on login page")
    print("="*60)
    app.run(host='0.0.0.0', port=8080, debug=False)
 
