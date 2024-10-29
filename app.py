from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_mysqldb import MySQL
from config import Config
app = Flask(__name__)
app.config.from_object(Config)
database = MySQL(app)
from datetime import datetime
import nltk
nltk.download('popular')
from nltk.stem import WordNetLemmatizer
lemmatizer = WordNetLemmatizer()
import pickle
import numpy as np
from keras.models import load_model
model = load_model('model/models.h5')
import json
import random
intents = json.loads(open('model/intens.json').read())
words = pickle.load(open('model/texts.pkl','rb'))
classes = pickle.load(open('model/labels.pkl','rb'))

# Format waktu pada pesan
def format_datetime(value):
    date_obj = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    return date_obj.strftime('%H:%M %d-%m-%Y')
app.jinja_env.filters['formatdatetime'] = format_datetime

# Untuk validasi login
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
    else:
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
    else:
        return redirect(url_for('login'))

# Untuk membuka percakapan
@app.route('/messages/<int:conversation_id>')
def messages(conversation_id):
    if 'loggedin' in session:
        # Ambil title percakapan dari conversation
        with database.connection.cursor() as cur:
            cur.execute("SELECT title, id FROM conversations WHERE id = %s", [conversation_id])
            title = cur.fetchone()  # Mengambil satu baris, karena satu percakapan memiliki satu title
        # Ambil pesan-pesan dari messages
        with database.connection.cursor() as cur:
            cur.execute("SELECT sender, message, DATE_FORMAT(timestamp, '%%H:%%i %%d-%%m-%%Y') as formatted_time FROM messages WHERE conversation_id = %s ORDER BY timestamp ASC", [conversation_id])
            messages = cur.fetchall()  # Mengambil semua pesan dari percakapan
            return render_template('includes/messages.html', title=title, messages=messages)
    else:
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
    else:
        return redirect(url_for('login'))

# Untuk memecah kalimat menjadi kata - kata dan mengubah kata ke bentuk dasar
def clean_up_sentence(sentence):
    sentence_words = nltk.word_tokenize(sentence)
    sentence_words = [lemmatizer.lemmatize(word.lower()) for word in sentence_words]
    return sentence_words

# Membuat Bag of Words (Pengubah data teks menjadi angka 1 (jika sesuai) dan 0 (jika tidak sesuai) agar dapat dipahami oleh komputer)
def bow(sentence, words, show_details=True):
    sentence_words = clean_up_sentence(sentence)
    bag = [0]*len(words)  
    for s in sentence_words:
        for i,w in enumerate(words):
            if w == s: 
                bag[i] = 1
                if show_details:
                    print ("found in bag: %s" % w)
    return(np.array(bag))

# Untuk memprediksi maksud/keinginan dari kata - kata inputan pengguna dengan model yang sudah dibuat
def predict_class(sentence, model):
    p = bow(sentence, words,show_details=False)
    res = model.predict(np.array([p]))[0]
    ERROR_THRESHOLD = 0.25
    results = [[i,r] for i,r in enumerate(res) if r>ERROR_THRESHOLD]
    results.sort(key=lambda x: x[1], reverse=True)
    return_list = []
    for r in results:
        return_list.append({"intent": classes[r[0]], "probability": str(r[1])})
    return return_list

# Untuk menentukan respons chatbot yang relevan berdasarkan predisksi
def getResponse(ints, intents_json):
    tag = ints[0]['intent']
    list_of_intents = intents_json['intents']
    for i in list_of_intents:
        if(i['tag']== tag):
            result = random.choice(i['responses'])
            break
    return result

# Untuk menggabungkan proses predict dan respons
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
            database.connection.commit()
            cur.close()
            response = chatbot_response(user_message)
            return jsonify({"status": "success"}), 200
        return jsonify({"error": "Pesan Kosong"}), 400
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)