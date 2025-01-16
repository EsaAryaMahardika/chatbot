from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_mysqldb import MySQL
from config import Config
app = Flask(__name__)
app.config.from_object(Config)
database = MySQL(app)
from datetime import datetime
import nltk
from nltk.corpus import stopwords
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
import pickle
import numpy as np
from keras.models import load_model
import json
import os
import random
import re
factory = StemmerFactory()
stemmer = factory.create_stemmer()
model = load_model('model/models.keras')
stop_words = set(stopwords.words("indonesian"))
intents = json.loads(open('model/intents.json').read())
words = pickle.load(open('model/texts.pkl','rb'))
classes = pickle.load(open('model/labels.pkl','rb'))

# Format waktu pada pesan
def format_datetime(value):
    date_obj = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    return date_obj.strftime('%H:%M %d-%m-%Y')
app.jinja_env.filters['formatdatetime'] = format_datetime

# Untuk login
@app.route('/login', methods=['GET', 'POST'])
def login():
    # Untuk validasi login
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
            return redirect(url_for('login'))
    else:
        # Untuk ke halaman login
        return render_template('login.html')

# Untuk sign up
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        cur = database.connection.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE username = %s", (username,))
        user_exists = cur.fetchone()[0]
        if user_exists:
            flash('Username sudah terdaftar, silakan gunakan username lain.', 'danger')
            return redirect(url_for('signup'))
        if password == confirm_password:
            cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, password))
            database.connection.commit()
            cur.close()
            flash('Berhasil daftar! Anda bisa login untuk konsultasi', 'success')
            return redirect(url_for('login'))
        else:
            flash('Harap sesuaikan password anda!', 'danger')
            return redirect(url_for('signup'))
    else:
        return render_template('signup.html')

# Untuk membuka percakapan setelah login
@app.route('/')
def chatbot():
    if 'loggedin' in session:
        user_id = session.get('user_id')
        username = session.get('username')
        cur = database.connection.cursor()
        if username == "dokter":
            cur.execute("SELECT conversations.id AS id, conversations.title AS title, users.username AS username FROM conversations JOIN users ON conversations.user_id = users.id WHERE validate is NULL ORDER BY conversations.id DESC")
            conversations = cur.fetchall()
            cur.close()
            return render_template('chat.html', conversations=conversations, username=username)
        elif username == "admin":
            return redirect(url_for('admin'))
        else:
            cur.execute("SELECT id, title FROM conversations WHERE user_id = %s ORDER BY id DESC", [user_id])
            conversations = cur.fetchall()
            cur.close()
            return render_template('chat.html', conversations=conversations, username=username)
    else:
        flash('Silahkan login terlebih dahulu', 'danger')
        return redirect(url_for('login'))

# Untuk admin
@app.route('/admin', methods=['GET','POST'])
def admin():
    username = session.get('username')
    files = {
            'intents': os.path.join(os.getcwd(), 'model/intents.json'),
            'baku': os.path.join(os.getcwd(), 'model/baku.json')
        }
    if request.method == 'POST':
        file_to_update = request.form.get('file_to_update')
        updated_content = request.form.get(file_to_update)
        if file_to_update and updated_content:
            try:
                json_data = json.loads(updated_content)
                with open(files[file_to_update.split('_')[0]], 'w') as json_file:
                    json.dump(json_data, json_file, indent=4)
                flash(f"{file_to_update} berhasil diperbarui!", "success")
            except json.JSONDecodeError:
                flash("Format JSON tidak valid!", "danger")
            except Exception as e:
                flash(f"Error: {e}", "danger")
        else:
            flash("Data yang dikirim tidak valid.", "danger")
        return redirect(url_for('admin'))
    else:
        with open(files['intents'], 'r') as intents, open(files['baku'], 'r') as baku:
            intents_content = json.dumps(json.load(intents), indent=4)
            baku_content = json.dumps(json.load(baku), indent=4)
        return render_template('admin.html', intents_content=intents_content, baku_content=baku_content, username=username)

# Untuk validasi dokter
@app.route('/validate', methods=['POST'])
def validate():
    try:
        # Ambil data dari permintaan AJAX
        data = request.get_json()
        is_valid = data.get('is_valid')
        if is_valid is None:
            return jsonify({"error": "Data is_valid tidak ditemukan"}), 400
        conversation_id = data.get('conversation_id')
        cur = database.connection.cursor()
        cur.execute(
            "UPDATE conversations SET validate = %s WHERE id = %s",
            (is_valid, conversation_id)
        )
        database.connection.commit()
        cur.close()
        return jsonify({"message": "Validasi berhasil diperbarui"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    else:
        flash('Silahkan login terlebih dahulu', 'danger')
        return redirect(url_for('login'))

# Untuk membuka percakapan
@app.route('/messages/<int:conversation_id>')
def messages(conversation_id):
    if 'loggedin' in session:
        username = session.get('username')
        # Ambil title percakapan dari conversation
        with database.connection.cursor() as cur:
            cur.execute("SELECT conversations.id AS id, conversations.title AS title, users.username AS username FROM conversations JOIN users ON conversations.user_id = users.id WHERE conversations.id = %s", [conversation_id])
            title = cur.fetchone()  # Mengambil satu baris, karena satu percakapan memiliki satu title
        # Ambil pesan-pesan dari messages
        with database.connection.cursor() as cur:
            cur.execute("SELECT sender, message, DATE_FORMAT(timestamp, '%%H:%%i %%d-%%m-%%Y') as formatted_time FROM messages WHERE conversation_id = %s ORDER BY timestamp ASC", [conversation_id])
            messages = cur.fetchall()  # Mengambil semua pesan dari percakapan
            return render_template('includes/messages.html', title=title, messages=messages, username=username)
    else:
        flash('Silahkan login terlebih dahulu', 'danger')
        return redirect(url_for('login'))
# Untuk menghapus percakapan
@app.route('/delete_conversation/<int:conversation_id>', methods=['POST'])
def delete_conversation(conversation_id):
    if 'loggedin' in session:
        cur = database.connection.cursor()
        cur.execute("DELETE FROM conversations WHERE id = %s", [conversation_id])
        database.connection.commit()
        cur.close()
        return jsonify({"status": "success"}), 200
    else:
        flash('Silahkan login terlebih dahulu', 'danger')
        return redirect(url_for('login'))

# Menyiapkan kumpulan kata baku
with open('model/baku.json') as f:
    normalization_data = json.load(f)

# Normalization
def normalize_word(word):
    return normalization_data.get(word, word)
# NLP
def nlp_steps(sentence):
    sentence = sentence.lower() # Case Folding
    sentence_words = nltk.word_tokenize(sentence) # Tokenization
    sentence_words = [normalize_word(word.lower()) for word in sentence_words] # Normalization
    sentence_words = [re.sub(r'[?!]', '', word) for word in sentence_words] # Menghapus karakter spesial
    sentence_words = [re.sub(r'\d+', '', word) for word in sentence_words] # Menghapus angka
    sentence_words = [word for word in sentence_words if word not in stop_words] # Filtering (menghapus stop words)
    sentence_words = [stemmer.stem(word) for word in sentence_words] # Stemming
    return sentence_words

# Bag of Words
def bow(sentence, words, show_details=True):
    sentence_words = nlp_steps(sentence)
    bag = [0]*len(words)  
    for s in sentence_words:
        for i,w in enumerate(words):
            if w == s: 
                bag[i] = 1
    return(np.array(bag))

# Untuk menghitung probabilitas hasil BoW menggunakan model yang sudah dibuat dan mengurutkan probabilitas tertinggi ke terendah
def predict_class(sentence, model):
    p = bow(sentence, words)
    res = model.predict(p.reshape(1, 1, -1))[0]
    ERROR_THRESHOLD = 0.25  # Ambang batas probabilitas
    results = [[i, r] for i, r in enumerate(res) if r > ERROR_THRESHOLD]
    if not results:
        return [{"intent": "fallback", "probability": "0"}]
    results.sort(key=lambda x: x[1], reverse=True)
    return [{"intent": classes[r[0]], "probability": str(r[1])} for r in results]

# Untuk memilih jawaban yang sesuai dengan dataset berdasarkan hasil predict tertinggi
def getResponse(ints, intents_json):
    tag = ints[0]['intent']
    list_of_intents = intents_json['intents']
    for i in list_of_intents:
        if(i['tag']== tag):
            result = random.choice(i['responses'])
            break
    return result

# Untuk menampilkan hasil getResponse    
def chatbot_response(msg):
    ints = predict_class(msg, model)
    res = getResponse(ints, intents)
    return res

# Untuk aksi setelah pengguna pengirim percakapan
@app.route('/send/<int:conversation_id>', methods=['POST'])
def send(conversation_id):
    if 'loggedin' in session:
        data = request.get_json()
        user_message = data.get('message')
        sender = 'user'
        if user_message:
            user_id = session.get('user_id')
            cur = database.connection.cursor()
            cur.execute("INSERT INTO messages (conversation_id, message, sender) VALUES (%s, %s, %s)", (conversation_id, user_message, sender))
            bot_message = chatbot_response(user_message)
            cur.execute("INSERT INTO messages (conversation_id, message, sender) VALUES (%s, %s, 'bot')", (conversation_id, bot_message))
            database.connection.commit()
            cur.close()
            return jsonify({"response": bot_message})
        return jsonify({"error": "Pesan Kosong"}), 400
    flash('Silahkan login terlebih dahulu', 'danger')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)