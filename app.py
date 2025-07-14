from flask import Flask, render_template, request, redirect, url_for, flash, session, get_flashed_messages, Response
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
import cv2
import numpy as np
from datetime import datetime
import os
import random
from ultralytics import YOLO

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Konfigurasi database
db_config = {
    'host': 'localhost',
    'user': 'root',  # Ganti dengan user MySQL Anda
    'password': '',  # Ganti dengan password MySQL Anda
    'database': 'proctoring_ujian'  # Ganti dengan nama database Anda
}

mysql = mysql.connector.connect(**db_config)

# Load model YOLOv11
model = YOLO("best.pt")  # Pastikan best.pt ada di direktori project

def generate_frames(user_id, ujian_id):
    cap = cv2.VideoCapture(0)
    cur = mysql.cursor(dictionary=True)

    # Ensure the evidence folder exists
    bukti_dir = os.path.join("static", "bukti")
    if not os.path.exists(bukti_dir):
        os.makedirs(bukti_dir)

    while True:
        success, frame = cap.read()
        if not success:
            break

        results = model(frame)
        bentuk_kecurangan = set()
        valid_frame = False  # Flag to check if any valid detections are found

        for result in results:
            boxes = result.boxes
            for box in boxes:
                confidence = float(box.conf)

                # Only consider detections with confidence >= 0.6
                if confidence < 0.6:
                    continue

                cls_id = int(box.cls)
                label = model.names[cls_id]
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                label_lower = label.lower()

                color = (0, 255, 255)
                if label_lower == 'smartphone':
                    color = (0, 0, 255)
                elif label_lower == 'kertas':
                    color = (255, 0, 0)
                elif label_lower == 'menoleh':
                    color = (0, 165, 255)

                if label_lower in ['smartphone', 'kertas', 'menoleh']:
                    bentuk_kecurangan.add(label)
                    valid_frame = True  # Set flag to true if valid detection is found

                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                text = f"{label} {confidence:.2f}"
                cv2.putText(frame, text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Save evidence only if cheating is detected and valid detection is found
        if valid_frame and bentuk_kecurangan:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            image_filename = f"cheating_capture_{timestamp}.jpg"
            image_path = os.path.join(bukti_dir, image_filename)
            cv2.imwrite(image_path, frame)
            print(f"Saved image: {image_path}")

            waktu = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            bukti = image_path
            for label in bentuk_kecurangan:
                try:
                    cur.execute("INSERT INTO proctoring (waktu, bentuk_kecurangan, bukti, user_id, ujian_id, dosen_id) VALUES (%s, %s, %s, %s, %s, %s)",
                                (waktu, label, bukti, user_id, ujian_id, user_id))  # Ganti user_id dengan dosen_id jika sudah diambil
                    mysql.commit()
                except Exception as e:
                    print(f"Error inserting into proctoring table: {e}")
                    mysql.rollback()

        # Encode frame for streaming
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    cur.close()
        
@app.route('/video_feed/<int:user_id>/<int:ujian_id>')
def video_feed(user_id, ujian_id):
    return Response(generate_frames(user_id, ujian_id),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['email']
        password = request.form['password']

        cur = mysql.cursor(dictionary=True)
        cur.execute("SELECT id, nama, email, role, password, kelas_id FROM users WHERE email = %s", (username,))
        user = cur.fetchone()
        cur.close()

        if user and check_password_hash(user['password'], password):
            session['role'] = user['role']
            session['nama'] = user['nama']
            session['email'] = user['email']
            session['kelas_id'] = user['kelas_id']
            session['id'] = user['id']  # STORE THE USER ID IN THE SESSION!

            # Fetch kelas_nama based on kelas_id
            cur = mysql.cursor(dictionary=True)
            cur.execute("SELECT kelas FROM kelas WHERE id = %s", (user['kelas_id'],))
            kelas_data = cur.fetchone()
            if kelas_data:
                session['kelas_nama'] = kelas_data['kelas']
            cur.close()

            return redirect(url_for('dashboard'))

        flash("Login gagal, periksa email dan password!", "danger")
        return redirect(url_for('login'))

    return render_template('index.html')

@app.route('/logout')
def logout():
    session.pop('role', None)  # Remove the role from session
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'role' in session:
        cur = mysql.cursor(dictionary=True)

        # Ambil data umum untuk admin
        cur.execute("SELECT COUNT(*) AS total FROM mata_kuliah")
        total_matkul = cur.fetchone()['total']

        cur.execute("SELECT COUNT(*) AS total FROM kelas")
        total_kelas = cur.fetchone()['total']

        cur.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'admin'")
        total_admin = cur.fetchone()['total']

        cur.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'dosen'")
        total_dosen = cur.fetchone()['total']

        cur.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'mahasiswa'")
        total_mahasiswa = cur.fetchone()['total']

        # ================== DOSEN ==================
        if session['role'] == 'dosen':
            cur.execute("SELECT COUNT(*) AS total FROM ujian WHERE dosen_id = %s", (session['id'],))
            total_ujian = cur.fetchone()['total']

            cur.execute("""
                SELECT COUNT(*) AS total
                FROM proctoring p
                JOIN ujian u ON p.ujian_id = u.id
                WHERE u.dosen_id = %s
            """, (session['id'],))
            total_proctoring = cur.fetchone()['total']

            cur.close()

            return render_template('dashboard_dosen.html',
                                   user=session.get('nama'),
                                   total_ujian=total_ujian,
                                   total_proctoring=total_proctoring)

        # ================== MAHASISWA ==================
        elif session['role'] == 'mahasiswa':
            kelas_id = session.get('kelas_id')
            total_ujian_mahasiswa = 0

            if kelas_id:
                cur.execute("SELECT COUNT(*) AS total FROM ujian WHERE kelas_id = %s", (kelas_id,))
                total_ujian_mahasiswa = cur.fetchone()['total']

            cur.close()

            return render_template('dashboard_mahasiswa.html',
                                   user=session.get('nama'),
                                   total_ujian=total_ujian_mahasiswa)

        # ================== ADMIN ==================
        elif session['role'] == 'admin':
            cur.close()
            return render_template('dashboard_admin.html',
                                   user=session.get('nama'),
                                   total_matkul=total_matkul,
                                   total_kelas=total_kelas,
                                   total_admin=total_admin,
                                   total_dosen=total_dosen,
                                   total_mahasiswa=total_mahasiswa)

    return redirect(url_for('login'))

@app.route('/edit-profile', methods=['GET', 'POST'])
def edit_profile():
    user_id = session.get('id')
    
    if not user_id:
        flash("Anda harus login untuk mengedit profil.", "danger")
        return redirect(url_for('login'))

    cur = mysql.cursor(dictionary=True)

    if request.method == 'POST':
        nama = request.form['nama']
        email = request.form['email']
        no_hp = request.form['no_hp']
        alamat = request.form['alamat']
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Fetch the current password from the database
        cur.execute("SELECT password FROM users WHERE id = %s", (user_id,))
        user_data = cur.fetchone()

        # Update user info
        try:
            query = """
                UPDATE users 
                SET nama = %s, email = %s, no_hp = %s, alamat = %s 
                WHERE id = %s
            """
            cur.execute(query, (nama, email, no_hp, alamat, user_id))

            # Check if current password is provided and verify it
            if current_password and user_data and check_password_hash(user_data['password'], current_password):
                # Update password if a new one is provided and matches confirmation
                if new_password and new_password == confirm_password:
                    hashed_password = generate_password_hash(new_password)
                    cur.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_password, user_id))
                else:
                    flash('Password baru dan konfirmasi tidak cocok.', 'danger')
                    mysql.rollback()
                    return redirect(url_for('edit_profile'))
            elif current_password:
                flash('Password saat ini tidak valid.', 'danger')
                mysql.rollback()
                return redirect(url_for('edit_profile'))

            mysql.commit()
            flash('Profil berhasil diperbarui!', 'success')
            return redirect(url_for('dashboard'))  # Redirect to the dashboard after success
        except Exception as e:
            mysql.rollback()
            flash(f'Error: {str(e)}', 'danger')

        return redirect(url_for('edit_profile'))

    # Fetch current user data
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_data = cur.fetchone()
    cur.close()

    return render_template('edit_profile.html', user=user_data)

@app.route('/data-mk', methods=['GET', 'POST'])
def matkul():
    cur = mysql.cursor(dictionary=True)

    if request.method == 'POST':
        kode_mk = request.form["kode_mk"]
        nama_mk = request.form["nama_mk"]

        # Insert ke database
        cur.execute("INSERT INTO mata_kuliah (kode_mk, nama_mk) VALUES (%s, %s)", (kode_mk, nama_mk))
        mysql.commit()

        flash("Data Mata Kuliah berhasil ditambahkan!", "success")  # Simpan pesan sukses
        return redirect(url_for("matkul"))

    cur.execute("SELECT id, kode_mk, nama_mk FROM mata_kuliah")
    data = cur.fetchall()

    messages = get_flashed_messages(with_categories=True)  # Ambil pesan flash
    return render_template("data_mk.html", data_mk=data, messages=messages)

@app.route('/edit-mk/<int:id>', methods=['POST'])
def edit_matkul(id):
    cur = mysql.cursor(dictionary=True)
    
    # Ambil data dari form
    kode_mk = request.form["kode_mk"]
    nama_mk = request.form["nama_mk"]
    
    # Update data di database
    cur.execute("""
        UPDATE mata_kuliah 
        SET kode_mk = %s, nama_mk = %s 
        WHERE id = %s
    """, (kode_mk, nama_mk, id))
    mysql.commit()
    
    flash("Data Mata Kuliah berhasil diperbarui!", "success")
    return redirect(url_for("matkul"))

@app.route('/delete-mk/<int:id>', methods=['POST'])
def delete_matkul(id):
    cur = mysql.cursor(dictionary=True)
    
    # Hapus data dari database
    cur.execute("DELETE FROM mata_kuliah WHERE id = %s", (id,))
    mysql.commit()
    
    flash("Data Mata Kuliah berhasil dihapus!", "success")
    return redirect(url_for("matkul"))

@app.route('/data-kelas', methods=['GET', 'POST'])
def kelas():
    cur = mysql.cursor(dictionary=True)

    if request.method == 'POST':
        nama_kelas = request.form["kelas"]

        # Insert ke database
        cur.execute("INSERT INTO kelas (kelas) VALUES (%s)", (nama_kelas,))
        mysql.commit()

        flash("Data Kelas berhasil ditambahkan!", "success")
        return redirect(url_for("kelas"))

    cur.execute("SELECT id, kelas FROM kelas")
    data = cur.fetchall()

    messages = get_flashed_messages(with_categories=True)
    return render_template("data_kelas.html", data_kelas=data, messages=messages)

@app.route('/edit-kelas/<int:id>', methods=['POST'])
def edit_kelas(id):
    cur = mysql.cursor(dictionary=True)

    nama_kelas = request.form["kelas"]

    cur.execute("UPDATE kelas SET kelas = %s WHERE id = %s", (nama_kelas, id))
    mysql.commit()

    flash("Data Kelas berhasil diperbarui!", "success")
    return redirect(url_for("kelas"))

@app.route('/delete-kelas/<int:id>', methods=['POST'])
def delete_kelas(id):
    cur = mysql.cursor(dictionary=True)

    cur.execute("DELETE FROM kelas WHERE id = %s", (id,))
    mysql.commit()

    flash("Data Kelas berhasil dihapus!", "success")
    return redirect(url_for("kelas"))

@app.route('/data-admin', methods=['GET', 'POST'])
def admin():
    cur = mysql.cursor(dictionary=True)
    if request.method == 'POST':
        nama = request.form['nama']
        email = request.form['email']
        password = request.form['password']

        # Hash password sebelum disimpan
        hashed_password = generate_password_hash(password)

        try:
            query = """
            INSERT INTO users (nama, email, password, role, nip, no_hp, alamat, jabatan, nim, prodi) 
            VALUES (%s, %s, %s, %s, NULL, NULL, NULL, NULL, NULL, NULL)
            """
            values = (nama, email, hashed_password, 'admin')

            cur.execute(query, values)
            mysql.commit()

            flash('Data admin berhasil ditambahkan!', 'success')
        except Exception as e:
            mysql.rollback()
            flash(f'Error: {str(e)}', 'danger')

        return redirect(url_for('admin'))

    # Ambil data admin dari database untuk ditampilkan
    cur.execute("SELECT * FROM users WHERE role='admin'")
    data = cur.fetchall()
    cur.close()

    messages = get_flashed_messages(with_categories=True)  # Ambil pesan flash
    return render_template('data_admin.html', data_admin=data, messages=messages)

@app.route('/edit-admin/<int:id>', methods=['POST'])
def edit_admin(id):
    cur = mysql.cursor(dictionary=True)
    try:
        nama = request.form['nama']
        email = request.form['email']

        query = """
        UPDATE users SET nama=%s, email=%s
        WHERE id=%s AND role='admin'
        """
        values = (nama, email, id)
        
        cur.execute(query, values)
        mysql.commit()
        flash('Data admin berhasil diperbarui!', 'success')
    except Exception as e:
        mysql.rollback()
        flash(f'Error: {str(e)}', 'danger')
    finally:
        cur.close()
    
    return redirect(url_for('admin'))

@app.route('/delete-admin/<int:id>', methods=['POST'])
def delete_admin(id):
    cur = mysql.cursor()
    try:
        cur.execute("DELETE FROM users WHERE id = %s AND role = 'admin'", (id,))
        mysql.commit()
        flash('Data admin berhasil dihapus!', 'success')
    except Exception as e:
        mysql.rollback()
        flash(f'Error: {str(e)}', 'danger')
    finally:
        cur.close()
    
    return redirect(url_for('admin'))

@app.route('/data-dosen', methods=['GET', 'POST'])
def dosen():
    cur = mysql.cursor(dictionary=True)
    if request.method == 'POST':
        nama = request.form['nama']
        nip = request.form['nip']
        email = request.form['email']
        password = request.form['password']
        no_hp = request.form['no_hp']
        alamat = request.form['alamat']
        jabatan = request.form['jabatan']

        # Hash password sebelum disimpan
        hashed_password = generate_password_hash(password)

        try:
            query = """
            INSERT INTO users (nama, nip, email, password, role, no_hp, alamat, jabatan, nim, prodi) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL)
            """
            values = (nama, nip, email, hashed_password, 'dosen', no_hp, alamat, jabatan)

            cur.execute(query, values)
            mysql.commit()

            flash('Data dosen berhasil ditambahkan!', 'success')
        except Exception as e:
            mysql.rollback()
            flash(f'Error: {str(e)}', 'danger')

        return redirect(url_for('dosen'))

    # Ambil data dosen dari database untuk ditampilkan
    cur.execute("SELECT * FROM users WHERE role='dosen'")
    data = cur.fetchall()
    cur.close()

    messages = get_flashed_messages(with_categories=True)  # Ambil pesan flash
    return render_template('data_dosen.html', data_dosen=data, messages=messages)

@app.route('/edit-dosen/<int:id>', methods=['POST'])
def edit_dosen(id):
    cur = mysql.cursor(dictionary=True)
    try:
        nama = request.form['nama']
        nip = request.form['nip']
        email = request.form['email']
        no_hp = request.form['no_hp']
        alamat = request.form['alamat']
        jabatan = request.form['jabatan']

        query = """
        UPDATE users SET nama=%s, nip=%s, email=%s, no_hp=%s, alamat=%s, jabatan=%s
        WHERE id=%s AND role='dosen'
        """
        values = (nama, nip, email, no_hp, alamat, jabatan, id)
        
        cur.execute(query, values)
        mysql.commit()
        flash('Data dosen berhasil diperbarui!', 'success')
    except Exception as e:
        mysql.rollback()
        flash(f'Error: {str(e)}', 'danger')
    finally:
        cur.close()
    
    return redirect(url_for('dosen'))

@app.route('/delete-dosen/<int:id>', methods=['POST'])
def delete_dosen(id):
    cur = mysql.cursor()
    try:
        cur.execute("DELETE FROM users WHERE id = %s AND role = 'dosen'", (id,))
        mysql.commit()
        flash('Data dosen berhasil dihapus!', 'success')
    except Exception as e:
        mysql.rollback()
        flash(f'Error: {str(e)}', 'danger')
    finally:
        cur.close()
    
    return redirect(url_for('dosen'))

@app.route('/data-mahasiswa', methods=['GET', 'POST'])
def mahasiswa():
    cur = mysql.cursor(dictionary=True)
    if request.method == 'POST':
        nama = request.form['nama']
        nim = request.form['nim']
        email = request.form['email']
        password = request.form['password']
        no_hp = request.form['no_hp']
        alamat = request.form['alamat']
        prodi = request.form['prodi']
        kelas_id = request.form['kelas']  # New field for kelas
        
        # Hash password sebelum disimpan
        hashed_password = generate_password_hash(password)
        
        try:
            query = """
            INSERT INTO users (nama, nim, email, password, role, no_hp, alamat, prodi, nip, jabatan, kelas_id) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, %s)
            """
            values = (nama, nim, email, hashed_password, 'mahasiswa', no_hp, alamat, prodi, kelas_id)

            cur.execute(query, values)
            mysql.commit()

            flash('Data mahasiswa berhasil ditambahkan!', 'success')
        except Exception as e:
            mysql.rollback()
            flash(f'Error: {str(e)}', 'danger')

        return redirect(url_for('mahasiswa'))
    
    # Ambil data mahasiswa dari database untuk ditampilkan
    cur.execute("""
    SELECT users.*, kelas.kelas AS kelas_nama
    FROM users
    LEFT JOIN kelas ON users.kelas_id = kelas.id
    WHERE users.role = 'mahasiswa'
""")

    data = cur.fetchall()

    # Ambil data kelas untuk dropdown
    cur.execute("SELECT * FROM kelas")  # Assuming "kelas" is the name of the table
    kelas_data = cur.fetchall()
    
    cur.close()

    messages = get_flashed_messages(with_categories=True)  # Ambil pesan flash
    return render_template('data_mahasiswa.html', data_mahasiswa=data, messages=messages, kelas_data=kelas_data)

@app.route('/edit-mahasiswa/<int:id>', methods=['POST'])
def edit_mahasiswa(id):
    cur = mysql.cursor(dictionary=True)
    try:
        nama = request.form['nama']
        nim = request.form['nim']
        email = request.form['email']
        no_hp = request.form['no_hp']
        alamat = request.form['alamat']
        prodi = request.form['prodi']
        kelas_id = request.form['kelas']  # New field for kelas

        query = """
        UPDATE users SET nama=%s, nim=%s, email=%s, no_hp=%s, alamat=%s, prodi=%s, kelas_id=%s
        WHERE id=%s AND role='mahasiswa'
        """
        values = (nama, nim, email, no_hp, alamat, prodi, kelas_id, id)
        
        cur.execute(query, values)
        mysql.commit()
        flash('Data mahasiswa berhasil diperbarui!', 'success')
    except Exception as e:
        mysql.rollback()
        flash(f'Error: {str(e)}', 'danger')
    finally:
        cur.close()
    
    return redirect(url_for('mahasiswa'))

@app.route('/delete-mahasiswa/<int:id>', methods=['POST'])
def delete_mahasiswa(id):
    cur = mysql.cursor()
    try:
        cur.execute("DELETE FROM users WHERE id = %s AND role = 'mahasiswa'", (id,))
        mysql.commit()
        flash('Data mahasiswa berhasil dihapus!', 'success')
    except Exception as e:
        mysql.rollback()
        flash(f'Error: {str(e)}', 'danger')
    finally:
        cur.close()
    
    return redirect(url_for('mahasiswa'))

# Manajemen Ujian
@app.route('/manajemen-ujian', methods=['GET', 'POST'])
def manajemen_ujian():
    cur = mysql.cursor(dictionary=True)
    
    user_id = session.get('id')  # Get the logged-in user's ID

    if request.method == 'POST':
        nama_ujian = request.form['nama_ujian']
        matakuliah_id = request.form['matakuliah_id']
        kelas_id = request.form['kelas_id']
        
        acak_soal = 1 if request.form.get('acak_soal') == 'Ya' else 0
        
        # Remove tampilkan_hasil from here
        # waktu_mulai and waktu_selesai remain the same
        waktu_mulai = request.form['waktu_mulai']
        waktu_selesai = request.form['waktu_selesai']

        try:
            query = """
                INSERT INTO ujian 
                (nama_ujian, matakuliah_id, kelas_id, acak_soal, waktu_mulai, waktu_selesai, dosen_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cur.execute(query, (
                nama_ujian, matakuliah_id, kelas_id, acak_soal, 
                waktu_mulai, waktu_selesai, user_id  # Associate the exam with the logged-in lecturer
            ))
            mysql.commit()
            flash('Ujian berhasil ditambahkan!', 'success')
        except Exception as e:
            mysql.rollback()
            flash(f'Error: {str(e)}', 'danger')

        return redirect(url_for('manajemen_ujian'))

    # Fetch exam data for the logged-in lecturer
    cur.execute("""
    SELECT ujian.*, mata_kuliah.nama_mk, kelas.kelas AS nama_kelas
    FROM ujian 
    JOIN mata_kuliah ON ujian.matakuliah_id = mata_kuliah.id
    JOIN kelas ON ujian.kelas_id = kelas.id
    WHERE ujian.dosen_id = %s
    """, (user_id,))
    
    data_ujian = cur.fetchall()

    # Fetch all courses for dropdown
    cur.execute("SELECT id, nama_mk FROM mata_kuliah")
    mata_kuliah = cur.fetchall()

    # Fetch all kelas for dropdown
    cur.execute("SELECT id, kelas FROM kelas")
    kelas_data = cur.fetchall()

    cur.close()

    messages = get_flashed_messages(with_categories=True)
    return render_template('manajemen_ujian.html', data_ujian=data_ujian, mata_kuliah=mata_kuliah, kelas_data=kelas_data, messages=messages)

@app.route('/edit-ujian/<int:id>', methods=['POST'])
def edit_ujian(id):
    cur = mysql.cursor(dictionary=True)
    try:
        nama_ujian = request.form['nama_ujian']
        matakuliah_id = request.form['matakuliah_id']
        kelas_id = request.form['kelas_id']  # Ambil kelas_id dari form
        
        acak_soal = 1 if request.form.get('acak_soal') == 'Ya' else 0
        
        print(f"Editing: acak_soal: {acak_soal}")  # Debugging
        
        waktu_mulai = request.form['waktu_mulai']
        waktu_selesai = request.form['waktu_selesai']

        query = """
        UPDATE ujian
        SET nama_ujian=%s, matakuliah_id=%s, kelas_id=%s, acak_soal=%s, waktu_mulai=%s, waktu_selesai=%s
        WHERE id=%s
        """
        values = (nama_ujian, matakuliah_id, kelas_id, acak_soal, waktu_mulai, waktu_selesai, id)
        
        cur.execute(query, values)
        mysql.commit()
        flash('Data ujian berhasil diperbarui!', 'success')
    except Exception as e:
        mysql.rollback()
        flash(f'Error: {str(e)}', 'danger')
    finally:
        cur.close()
    
    return redirect(url_for('manajemen_ujian'))

@app.route('/delete-ujian/<int:id>', methods=['POST'])
def delete_ujian(id):
    cur = mysql.cursor()
    try:
        cur.execute("DELETE FROM ujian WHERE id = %s", (id,))
        mysql.commit()
        flash('Data ujian berhasil dihapus!', 'success')
    except Exception as e:
        mysql.rollback()
        flash(f'Error: {str(e)}', 'danger')
    finally:
        cur.close()
    
    return redirect(url_for('manajemen_ujian'))

@app.route('/manajemen-proctoring', methods=['GET', 'POST'])
def manajemen_proctoring():
    cur = mysql.cursor(dictionary=True)

    # Ambil user_id dari session
    user_id = session.get('id')

    # Handle form POST untuk menambahkan data proctoring
    if request.method == 'POST':
        waktu = request.form['waktu']
        bentuk_kecurangan = request.form['bentuk_kecurangan']
        bukti = request.form['bukti']
        ujian_id = request.form['ujian_id']

        try:
            query = """
                INSERT INTO proctoring (waktu, bentuk_kecurangan, bukti, user_id, ujian_id)
                VALUES (%s, %s, %s, %s, %s)
            """
            cur.execute(query, (waktu, bentuk_kecurangan, bukti, user_id, ujian_id))
            mysql.commit()
            flash('Data proctoring berhasil ditambahkan!', 'success')
        except Exception as e:
            mysql.rollback()
            flash(f'Error: {str(e)}', 'danger')

        return redirect(url_for('manajemen_proctoring'))

    # Handle pencarian
    search = request.args.get('search', '')

    if search:
        like = f"%{search}%"
        query = """
        SELECT p.*, u.nama AS user_name, uj.nama_ujian AS ujian_name, k.kelas AS kelas_name
        FROM proctoring p
        JOIN users u ON p.user_id = u.id
        JOIN ujian uj ON p.ujian_id = uj.id
        JOIN kelas k ON uj.kelas_id = k.id
        WHERE uj.dosen_id = %s
          AND (
              u.nama LIKE %s OR
              uj.nama_ujian LIKE %s OR
              k.kelas LIKE %s
          )
        ORDER BY p.waktu DESC
        """
        cur.execute(query, (user_id, like, like, like))
    else:
        query = """
        SELECT p.*, u.nama AS user_name, uj.nama_ujian AS ujian_name, k.kelas AS kelas_name
        FROM proctoring p
        JOIN users u ON p.user_id = u.id
        JOIN ujian uj ON p.ujian_id = uj.id
        JOIN kelas k ON uj.kelas_id = k.id
        WHERE uj.dosen_id = %s
        ORDER BY p.waktu DESC
        """
        cur.execute(query, (user_id,))

    data_proctoring = cur.fetchall()
    cur.close()

    return render_template(
    'manajemen_proctoring.html',
    data_proctoring=data_proctoring,
    messages=get_flashed_messages(with_categories=True)
)

@app.route('/delete-proctoring/<int:id>', methods=['POST'])
def delete_proctoring(id):
    cur = mysql.cursor()
    try:
        cur.execute("DELETE FROM proctoring WHERE id = %s", (id,))
        mysql.commit()
        flash('Data proctoring berhasil dihapus!', 'success')
    except Exception as e:
        mysql.rollback()
        flash(f'Error: {str(e)}', 'danger')
    finally:
        cur.close()
    
    return redirect(url_for('manajemen_proctoring'))

@app.route('/tambah-ujian/<int:id>', methods=['GET', 'POST'])
def tambah_ujian(id):
    cur = mysql.cursor(dictionary=True)
    cur.execute("""
        SELECT ujian.*, mata_kuliah.nama_mk, kelas.kelas AS nama_kelas 
        FROM ujian 
        JOIN mata_kuliah ON ujian.matakuliah_id = mata_kuliah.id 
        JOIN kelas ON ujian.kelas_id = kelas.id
        WHERE ujian.id = %s
    """, (id,))
    ujian = cur.fetchone()

    if ujian is None:
        flash('Ujian tidak ditemukan!', 'danger')
        return redirect(url_for('manajemen_ujian'))

    # Fetch questions related to the ujian
    cur.execute("SELECT * FROM soal WHERE ujian_id = %s", (id,))
    soal_list = cur.fetchall()
    cur.close()

    return render_template('tambah_ujian.html', ujian=ujian, soal_list=soal_list)

@app.route('/tambah-soal/<int:ujian_id>', methods=['GET', 'POST'])
def tambah_soal(ujian_id):
    if request.method == 'POST':
        soal = request.form['soal']
        pilihan_a = request.form['pilihan_a']
        pilihan_b = request.form['pilihan_b']
        pilihan_c = request.form.get('pilihan_c', '')
        pilihan_d = request.form.get('pilihan_d', '')
        pilihan_e = request.form.get('pilihan_e', '')
        jawaban_benar = request.form['jawaban_benar']
        bobot_nilai = request.form['bobot_nilai']  # New field for score weight

        try:
            cur = mysql.cursor()
            query = """
                INSERT INTO soal (ujian_id, soal, pilihan_a, pilihan_b, pilihan_c, pilihan_d, pilihan_e, jawaban_benar, bobot_nilai) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cur.execute(query, (ujian_id, soal, pilihan_a, pilihan_b, pilihan_c, pilihan_d, pilihan_e, jawaban_benar, bobot_nilai))
            mysql.commit()
            flash('Soal berhasil ditambahkan!', 'success')
        except Exception as e:
            mysql.rollback()
            flash(f'Error: {str(e)}', 'danger')
        finally:
            cur.close()
        
        return redirect(url_for('tambah_ujian', id=ujian_id))

    return render_template('tambah_soal.html', ujian_id=ujian_id)

@app.route('/edit-soal/<int:id>', methods=['GET', 'POST'])
def edit_soal(id):
    cur = mysql.cursor(dictionary=True)
    
    if request.method == 'POST':
        soal = request.form['soal']
        pilihan_a = request.form['pilihan_a']
        pilihan_b = request.form['pilihan_b']
        pilihan_c = request.form.get('pilihan_c', '')
        pilihan_d = request.form.get('pilihan_d', '')
        pilihan_e = request.form.get('pilihan_e', '')
        jawaban_benar = request.form['jawaban_benar']
        bobot_nilai = request.form['bobot_nilai']

        try:
            query = """
                UPDATE soal 
                SET soal=%s, pilihan_a=%s, pilihan_b=%s, pilihan_c=%s, pilihan_d=%s, pilihan_e=%s, jawaban_benar=%s, bobot_nilai=%s 
                WHERE id=%s
            """
            cur.execute(query, (soal, pilihan_a, pilihan_b, pilihan_c, pilihan_d, pilihan_e, jawaban_benar, bobot_nilai, id))
            mysql.commit()
            flash('Soal berhasil diperbarui!', 'success')
        except Exception as e:
            mysql.rollback()
            flash(f'Error: {str(e)}', 'danger')
        finally:
            cur.close()
        
        return redirect(url_for('tambah_ujian', id=request.form['ujian_id']))

    # Fetch the current question data for editing
    cur.execute("SELECT * FROM soal WHERE id = %s", (id,))
    soal_data = cur.fetchone()
    cur.close()

    return render_template('edit_soal.html', soal=soal_data)

@app.route('/delete-soal/<int:id>', methods=['POST'])
def delete_soal(id):
    cur = mysql.cursor()
    try:
        cur.execute("DELETE FROM soal WHERE id = %s", (id,))
        mysql.commit()
        flash('Soal berhasil dihapus!', 'success')
    except Exception as e:
        mysql.rollback()
        flash(f'Error: {str(e)}', 'danger')
    finally:
        cur.close()
    
    return redirect(url_for('tambah_ujian', id=request.form['ujian_id']))

@app.route('/ujian-mahasiswa')
def ujian_mahasiswa():
    cur = mysql.cursor(dictionary=True)

    # Ambil informasi kelas dan user dari session
    kelas_id = session.get('kelas_id')
    kelas_nama = session.get('kelas_nama')
    user_id = session.get('id')

    ujian_list = []

    # Jika tidak ada kelas, tampilkan pesan
    if not kelas_id:
        flash("Anda tidak memiliki kelas yang terdaftar. Tidak ada ujian yang tersedia.", "warning")
        kelas_nama = "Tidak Ada Kelas"
    else:
        # Ambil daftar ujian berdasarkan kelas
        cur.execute("""
            SELECT ujian.*, mata_kuliah.nama_mk
            FROM ujian
            JOIN mata_kuliah ON ujian.matakuliah_id = mata_kuliah.id
            WHERE ujian.kelas_id = %s
        """, (kelas_id,))
        ujian_list = cur.fetchall()

        # Tambahkan status is_submitted dan score untuk setiap ujian
        for ujian in ujian_list:
            cur.execute("""
                SELECT score FROM hasil_ujian
                WHERE ujian_id = %s AND user_id = %s
                LIMIT 1
            """, (ujian['id'], user_id))
            hasil = cur.fetchone()

            # Jika sudah mengerjakan, tambahkan flag dan nilai
            if hasil:
                ujian['is_submitted'] = True
                ujian['score'] = hasil['score']
            else:
                ujian['is_submitted'] = False
                ujian['score'] = None

    cur.close()

    # Kirim waktu saat ini ke template
    current_time = datetime.now()

    return render_template(
        'ujian_mahasiswa.html',
        ujian_list=ujian_list,
        kelas_nama=kelas_nama,
        current_time=current_time
    )

@app.route('/mulai-ujian/<int:ujian_id>')
def mulai_ujian(ujian_id):
    cur = mysql.cursor(dictionary=True)
    
    # Fetch the exam details
    cur.execute("SELECT * FROM ujian WHERE id = %s", (ujian_id,))
    ujian = cur.fetchone()

    if ujian is None:
        flash('Ujian tidak ditemukan!', 'danger')
        return redirect(url_for('ujian_mahasiswa'))

    # Fetch questions related to the exam
    cur.execute("SELECT * FROM soal WHERE ujian_id = %s", (ujian_id,))
    questions = cur.fetchall()

    # Randomize the order of the questions if "acak_soal" is set
    if ujian['acak_soal']:
        random.shuffle(questions)

    # Calculate the exam duration
    waktu_mulai = ujian['waktu_mulai']
    waktu_selesai = ujian['waktu_selesai']

    duration = waktu_selesai - waktu_mulai
    hours, remainder = divmod(duration.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    ujian['duration'] = f"{int(hours)} jam {int(minutes)} menit {int(seconds)} detik"
    ujian['waktu_selesai_timestamp'] = int(waktu_selesai.timestamp() * 1000)  # in milliseconds

    cur.close()

    return render_template('ujian.html', questions=questions, ujian=ujian)

@app.route('/submit-ujian', methods=['POST'])
def submit_ujian():
    cur = mysql.cursor()
    score = 0
    try:
        user_id = session.get('id')
        ujian_id = request.form.get('ujian_id')

        if not user_id or not ujian_id:
            return "User atau ujian tidak valid.", 400

        # Process each question
        for question_id, answer in request.form.items():
            if question_id.startswith('q'):
                soal_id = question_id[1:]

                cur.execute("SELECT jawaban_benar, bobot_nilai FROM soal WHERE id = %s", (soal_id,))
                result = cur.fetchone()
                if result:
                    correct_answer, bobot_nilai = result
                    if answer == correct_answer:
                        score += bobot_nilai

                # Save the student's answer
                cur.execute("""
                    INSERT INTO jawaban_ujian (ujian_id, soal_id, users_id, jawaban_mahasiswa, waktu_jawab)
                    VALUES (%s, %s, %s, %s, NOW())
                """, (ujian_id, soal_id, user_id, answer))

        # Save the score
        cur.execute("""
            INSERT INTO hasil_ujian (ujian_id, user_id, score)
            VALUES (%s, %s, %s)
        """, (ujian_id, user_id, score))

        # Update the is_submitted status
        cur.execute("UPDATE ujian SET is_submitted = TRUE WHERE id = %s", (ujian_id,))

        mysql.commit()
        flash(f"Ujian dikumpulkan! Nilai Anda: {score}", "success")
        return redirect(url_for('ujian_mahasiswa'))

    except Exception as e:
        mysql.rollback()
        flash(f"Terjadi kesalahan: {e}", "danger")
        return "Terjadi kesalahan saat memproses jawaban.", 500

    finally:
        cur.close()

@app.route('/riwayat-ujian')
def riwayat_ujian():
    user_id = session.get('id')  # Get the logged-in user's ID
    if not user_id:
        flash("Anda harus login untuk melihat riwayat ujian.", "danger")
        return redirect(url_for('login'))

    cur = mysql.cursor(dictionary=True)
    try:
        # Fetch the history of exams taken by the user
        query = """
            SELECT h.*, uj.nama_ujian, mk.nama_mk
            FROM hasil_ujian h
            JOIN ujian uj ON h.ujian_id = uj.id
            JOIN mata_kuliah mk ON uj.matakuliah_id = mk.id
            WHERE h.user_id = %s
        """
        cur.execute(query, (user_id,))
        riwayat = cur.fetchall()
    except Exception as e:
        flash(f"Error fetching exam history: {e}", "danger")
        riwayat = []
    finally:
        cur.close()

    return render_template('riwayat_ujian.html', riwayat=riwayat)

@app.route('/hasil-ujian', methods=['GET'])
def hasil_ujian():
    cur = mysql.cursor(dictionary=True)
    
    user_id = session.get('id')
    search = request.args.get('search', '')

    try:
        if search:
            like = f"%{search}%"
            cur.execute("""
                SELECT h.*, uj.nama_ujian, u.nama AS mahasiswa_nama, k.kelas AS kelas_name
                FROM hasil_ujian h
                JOIN ujian uj ON h.ujian_id = uj.id
                JOIN users u ON h.user_id = u.id
                JOIN kelas k ON uj.kelas_id = k.id
                WHERE uj.dosen_id = %s AND (
                    u.nama LIKE %s OR
                    uj.nama_ujian LIKE %s OR
                    k.kelas LIKE %s
                )
                ORDER BY h.id DESC
            """, (user_id, like, like, like))
        else:
            cur.execute("""
                SELECT h.*, uj.nama_ujian, u.nama AS mahasiswa_nama, k.kelas AS kelas_name
                FROM hasil_ujian h
                JOIN ujian uj ON h.ujian_id = uj.id
                JOIN users u ON h.user_id = u.id
                JOIN kelas k ON uj.kelas_id = k.id
                WHERE uj.dosen_id = %s
                ORDER BY h.id DESC
            """, (user_id,))
        
        results = cur.fetchall()

    except Exception as e:
        flash(f"Error fetching results: {e}", "danger")
        results = []

    finally:
        cur.close()

    return render_template('hasil_ujian.html', results=results)

if __name__ == '__main__':
    app.run(debug=True)