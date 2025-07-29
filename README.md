📌 Project Title: RANCANG BANGUN APLIKASI UJIAN ONLINE DENGAN FITUR DETEKSI PERILAKU MENCURIGAKAN MENGGUNAKAN YOLO

📖 Deskripsi

Proyek ini merupakan sistem ujian online berbasis web yang dilengkapi dengan fitur proctoring otomatis untuk mendeteksi perilaku mencurigakan selama ujian. Sistem dibangun menggunakan Flask sebagai backend dan mengintegrasikan deteksi objek secara real-time menggunakan YOLO (You Only Look Once).

⚙️ Fitur Utama

🎥 Live Kamera Ujian dengan deteksi otomatis
🧠 Deteksi perilaku mencurigakan berbasis YOLOv11
📸 Perekaman bukti pelanggaran (captures) ke dalam database
👤 Manajemen akun pengguna (admin, dosen, mahasiswa)
📄 Sistem soal & ujian online berbasis web dengan navigasi per soal
🔀 Opsi acak soal
📊 Rekap hasil ujian & laporan aktivitas peserta ujian

🧩 Library

1. Python 3.12.2
2. Flask
3. Werkzeug
4. mysql-connector-python
5. pandas
6. numpy
7. ultralytics
8. opencv-python


🛠️ Instalasi

1. Clone repo:

bash
git clone https://github.com/AudreySurya123/ExamVision.git

2. Install dependencies:

bash
pip freeze > requirements.txt 

💾 Database & Migrasi

bash
pip install mysql-connector-python
mysql -u root -p

Lalu masuk database mysql
CREATE DATABASE proctoring_ujian;
USE proctoring_ujian;

Masukkan query
CREATE TABLE kelas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kelas VARCHAR(50)
);

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nama VARCHAR(100),
    nim VARCHAR(50),
    email VARCHAR(100) UNIQUE,
    password VARCHAR(255),
    role ENUM('admin', 'dosen', 'mahasiswa'),
    no_hp VARCHAR(15),
    alamat TEXT,
    prodi VARCHAR(100),
    nip VARCHAR(50),
    jabatan VARCHAR(50),
    kelas_id INT,
    FOREIGN KEY (kelas_id) REFERENCES kelas(id) ON DELETE SET NULL
);

CREATE TABLE mata_kuliah (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kode_mk VARCHAR(50),
    nama_mk VARCHAR(100)
);

CREATE TABLE ujian (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nama_ujian VARCHAR(255),
    matakuliah_id INT,
    acak_soal ENUM('ya', 'tidak') DEFAULT 'tidak',
    waktu_mulai DATETIME,
    waktu_selesai DATETIME,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    kelas_id INT,
    dosen_id INT,
    is_submitted TINYINT(1) DEFAULT 0,
    FOREIGN KEY (matakuliah_id) REFERENCES mata_kuliah(id),
    FOREIGN KEY (kelas_id) REFERENCES kelas(id),
    FOREIGN KEY (dosen_id) REFERENCES users(id)
);

CREATE TABLE proctoring (
    id INT AUTO_INCREMENT PRIMARY KEY,
    waktu DATETIME,
    bentuk_kecurangan VARCHAR(255),
    bukti VARCHAR(255),
    user_id INT,
    ujian_id INT,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (ujian_id) REFERENCES ujian(id)
);

CREATE TABLE soal (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ujian_id INT,
    soal TEXT,
    pilihan_a TEXT,
    pilihan_b TEXT,
    pilihan_c TEXT,
    pilihan_d TEXT,
    pilihan_e TEXT,
    jawaban_benar VARCHAR(50),
    bobot_nilai INT,
    FOREIGN KEY (ujian_id) REFERENCES ujian(id)
);

CREATE TABLE hasil_ujian (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ujian_id INT,
    user_id INT,
    score INT,
    FOREIGN KEY (ujian_id) REFERENCES ujian(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE jawaban_ujian (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ujian_id INT,
    soal_id INT,
    users_id INT,
    jawaban_mahasiswa VARCHAR(50),
    waktu_jawab DATETIME,
    FOREIGN KEY (ujian_id) REFERENCES ujian(id),
    FOREIGN KEY (soal_id) REFERENCES soal(id),
    FOREIGN KEY (users_id) REFERENCES users(id)
);
