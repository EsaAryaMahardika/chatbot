from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_mysqldb import MySQL
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

database = MySQL(app)

# Untuk halaman login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        cur = database.connection.cursor()
        cur.execute("SELECT id, username FROM users WHERE username=%s AND password=%s", (username, password))
        user = cur.fetchone()
        cur.close()
        if user:
            session['loggedin'] = True
            session['user_id'] = user[0]
            session['username'] = user[1]
            return redirect(url_for('chatbot'))
        else:
            flash('Username atau password salah', 'danger')
    return render_template('login.html')

# Untuk membuka percakapan setelah login
@app.route('/')
def chatbot():
    if 'loggedin' in session:
        user_id = session.get('user_id')
        cur = database.connection.cursor()
        cur.execute("SELECT id, title FROM conversations WHERE user_id = %s ORDER BY id DESC", [user_id])
        conversations = cur.fetchall()
        cur.close()
        return render_template('chat.html', conversations=conversations)
    else:
        return redirect(url_for('login'))

# Untuk logout
@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('username', None)
    return redirect(url_for('login'))

# Untuk membuat percakapan baru
@app.route('/new-chat', methods=['POST'])
def new_chat():
    if 'loggedin' in session:
        user_id = session.get('user_id')
        # Penamaan percakapan
        cur = database.connection.cursor()
        cur.execute("SELECT COUNT(*) FROM conversations WHERE user_id = %s", [user_id])
        count = cur.fetchone()[0]
        conversation_name = f"Konsultasi {count + 1}"
        # Simpan percakapan baru
        cur.execute("INSERT INTO conversations (user_id, title) VALUES (%s, %s)", (user_id, conversation_name))
        database.connection.commit()
        # Ambil percakapan terbaru
        cur.execute("SELECT id, title FROM conversations WHERE user_id = %s ORDER BY id DESC", [user_id])
        conversations = cur.fetchall()
        cur.close()
        return render_template('includes/history.html', conversations=conversations)
    return redirect(url_for('login'))

# Untuk membuka percakapan
@app.route('/messages/<int:conversation_id>')
def messages(conversation_id):
    if 'loggedin' in session:
        cur = database.connection.cursor()
        cur.execute("SELECT * FROM messages WHERE conversation_id= %s", [conversation_id])
        message = cur.fetchall()
        cur.close()
        return render_template('includes/messages.html', message=message)
    return redirect(url_for('login'))

# Untuk menghapus percakapan
@app.route('/delete_conversation/<int:conversation_id>')
def delete_conversation(conversation_id):
    if 'loggedin' in session:
        cur = database.connection.cursor()
        cur.execute("DELETE FROM conversations WHERE id = %s", [conversation_id])
        database.connection.commit()
        cur.close()
        flash('Percakapan berhasil dihapus', 'success')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)