-- Initialize database for educational data warehouse
-- This script runs when the PostgreSQL container starts

-- Create the main database (if it doesn't exist - handled by POSTGRES_DB env var)
-- CREATE DATABASE education_dw;

-- Create Superset database
CREATE DATABASE superset_db;

-- Connect to the education_dw database and create schemas
\c education_dw;

-- Create schemas
CREATE SCHEMA IF NOT EXISTS raw_edu;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS intermediate;
CREATE SCHEMA IF NOT EXISTS marts;

-- Grant permissions to dbt_user
GRANT ALL PRIVILEGES ON SCHEMA raw_edu TO dbt_user;
GRANT ALL PRIVILEGES ON SCHEMA staging TO dbt_user;
GRANT ALL PRIVILEGES ON SCHEMA intermediate TO dbt_user;
GRANT ALL PRIVILEGES ON SCHEMA marts TO dbt_user;

-- Grant usage on schemas
GRANT USAGE ON SCHEMA raw_edu TO dbt_user;
GRANT USAGE ON SCHEMA staging TO dbt_user;
GRANT USAGE ON SCHEMA intermediate TO dbt_user;
GRANT USAGE ON SCHEMA marts TO dbt_user;

-- Set search path
ALTER USER dbt_user SET search_path TO marts,intermediate,staging,raw_edu,public;

-- Create initial raw tables
CREATE TABLE IF NOT EXISTS raw_edu.students (
    student_id SERIAL PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT UNIQUE,
    date_of_birth DATE,
    enrollment_date DATE,
    graduation_date DATE,
    student_status TEXT CHECK (student_status IN ('active', 'graduated', 'dropped', 'suspended')),
    gpa DECIMAL(3,2),
    major_id INT,
    advisor_id INT,
    address_id INT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_edu.courses (
    course_id SERIAL PRIMARY KEY,
    course_code TEXT UNIQUE NOT NULL,
    course_name TEXT NOT NULL,
    description TEXT,
    credits INT NOT NULL,
    department_id INT,
    prerequisite_course_id INT,
    difficulty_level INT CHECK (difficulty_level BETWEEN 1 AND 5),
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_edu.departments (
    department_id SERIAL PRIMARY KEY,
    department_name TEXT NOT NULL,
    department_code TEXT UNIQUE,
    head_faculty_id INT,
    budget DECIMAL(12,2),
    building_location TEXT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_edu.faculty (
    faculty_id SERIAL PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT UNIQUE,
    department_id INT,
    position TEXT,
    salary DECIMAL(10,2),
    hire_date DATE,
    office_number TEXT,
    research_interests TEXT[],
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_edu.enrollments (
    enrollment_id SERIAL PRIMARY KEY,
    student_id INT,
    course_id INT,
    semester_id INT,
    enrollment_date DATE,
    completion_date DATE,
    grade TEXT,
    grade_points DECIMAL(3,2),
    attendance_percentage DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_edu.semesters (
    semester_id SERIAL PRIMARY KEY,
    semester_name TEXT NOT NULL,
    academic_year TEXT,
    start_date DATE,
    end_date DATE,
    is_current BOOLEAN DEFAULT false,
    semester_type TEXT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_edu.class_sessions (
    session_id SERIAL PRIMARY KEY,
    course_id INT,
    faculty_id INT,
    semester_id INT,
    session_time TIME,
    session_date DATE,
    room_id INT,
    attendance_count INT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_edu.assignments (
    assignment_id SERIAL PRIMARY KEY,
    course_id INT,
    semester_id INT,
    assignment_name TEXT NOT NULL,
    assignment_type TEXT,
    due_date DATE,
    max_points DECIMAL(6,2),
    weight_percentage DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_edu.assignment_submissions (
    submission_id SERIAL PRIMARY KEY,
    assignment_id INT,
    student_id INT,
    submission_date TIMESTAMP,
    score DECIMAL(6,2),
    late_submission BOOLEAN DEFAULT false,
    feedback TEXT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_edu.financial_aid (
    aid_id SERIAL PRIMARY KEY,
    student_id INT,
    aid_type TEXT,
    amount DECIMAL(10,2),
    academic_year TEXT,
    disbursement_date DATE,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_edu.tuition_payments (
    payment_id SERIAL PRIMARY KEY,
    student_id INT,
    semester_id INT,
    amount DECIMAL(10,2),
    payment_date DATE,
    payment_method TEXT,
    late_fee DECIMAL(8,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT now()
);

-- Grant permissions on all tables
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA raw_edu TO dbt_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA raw_edu TO dbt_user;

-- Insert sample data
INSERT INTO raw_edu.departments (department_name, department_code, budget, building_location) VALUES
    ('Computer Science', 'CS', 2500000.00, 'Tech Building A'),
    ('Mathematics', 'MATH', 1800000.00, 'Science Hall'),
    ('Business Administration', 'BUS', 3200000.00, 'Business Center'),
    ('Psychology', 'PSYC', 1500000.00, 'Liberal Arts Building'),
    ('Engineering', 'ENG', 4000000.00, 'Engineering Complex')
ON CONFLICT (department_code) DO NOTHING;

INSERT INTO raw_edu.faculty (first_name, last_name, email, department_id, position, salary, hire_date, office_number) VALUES
    ('John', 'Smith', 'j.smith@edu.edu', 1, 'Professor', 95000.00, '2015-08-15', 'TA-201'),
    ('Sarah', 'Johnson', 's.johnson@edu.edu', 1, 'Associate Professor', 78000.00, '2018-01-10', 'TA-205'),
    ('Michael', 'Brown', 'm.brown@edu.edu', 2, 'Professor', 89000.00, '2012-09-01', 'SH-301'),
    ('Emily', 'Davis', 'e.davis@edu.edu', 3, 'Assistant Professor', 72000.00, '2020-08-20', 'BC-401'),
    ('Robert', 'Wilson', 'r.wilson@edu.edu', 5, 'Professor', 105000.00, '2010-01-15', 'EC-101')
ON CONFLICT (email) DO NOTHING;

INSERT INTO raw_edu.semesters (semester_name, academic_year, start_date, end_date, is_current, semester_type) VALUES
    ('Fall 2023', '2023-2024', '2023-08-28', '2023-12-15', false, 'Fall'),
    ('Spring 2024', '2023-2024', '2024-01-15', '2024-05-10', false, 'Spring'),
    ('Fall 2024', '2024-2025', '2024-08-26', '2024-12-13', true, 'Fall'),
    ('Spring 2025', '2024-2025', '2025-01-13', '2025-05-08', false, 'Spring')
ON CONFLICT DO NOTHING;

INSERT INTO raw_edu.courses (course_code, course_name, credits, department_id, difficulty_level) VALUES
    ('CS101', 'Introduction to Computer Science', 3, 1, 1),
    ('CS201', 'Data Structures and Algorithms', 4, 1, 3),
    ('CS301', 'Database Systems', 3, 1, 3),
    ('CS401', 'Machine Learning', 4, 1, 4),
    ('MATH101', 'Calculus I', 4, 2, 2),
    ('MATH201', 'Linear Algebra', 3, 2, 3),
    ('MATH301', 'Statistics', 3, 2, 2),
    ('BUS101', 'Introduction to Business', 3, 3, 1),
    ('BUS201', 'Marketing Principles', 3, 3, 2),
    ('BUS301', 'Financial Management', 4, 3, 3),
    ('PSYC101', 'General Psychology', 3, 4, 1),
    ('ENG101', 'Engineering Fundamentals', 4, 5, 2)
ON CONFLICT (course_code) DO NOTHING;

INSERT INTO raw_edu.students (first_name, last_name, email, date_of_birth, enrollment_date, student_status, gpa, major_id, address_id) VALUES
    ('Alice', 'Anderson', 'alice.anderson@student.edu', '2002-03-15', '2022-08-28', 'active', 3.75, 1, 1),
    ('Bob', 'Baker', 'bob.baker@student.edu', '2001-11-22', '2021-08-30', 'active', 3.20, 1, 2),
    ('Charlie', 'Chen', 'charlie.chen@student.edu', '2003-07-08', '2023-08-28', 'active', 3.90, 2, 3),
    ('Diana', 'Davis', 'diana.davis@student.edu', '2002-01-12', '2022-08-28', 'active', 3.45, 3, 4),
    ('Edward', 'Evans', 'edward.evans@student.edu', '2000-09-18', '2020-08-31', 'graduated', 3.60, 1, 5),
    ('Fiona', 'Foster', 'fiona.foster@student.edu', '2002-05-25', '2022-08-28', 'active', 3.85, 5, 6),
    ('George', 'Garcia', 'george.garcia@student.edu', '2003-12-03', '2023-08-28', 'active', 2.95, 4, 7),
    ('Hannah', 'Harris', 'hannah.harris@student.edu', '2001-06-14', '2021-08-30', 'active', 3.70, 2, 8)
ON CONFLICT (email) DO NOTHING;

-- Add some sample enrollments
INSERT INTO raw_edu.enrollments (student_id, course_id, semester_id, enrollment_date, grade, grade_points, attendance_percentage) VALUES
    (1, 1, 3, '2024-08-26', 'A', 3.7, 95.0),
    (1, 5, 3, '2024-08-26', 'B+', 3.3, 88.0),
    (2, 1, 3, '2024-08-26', 'B', 3.0, 82.0),
    (2, 2, 3, '2024-08-26', 'A-', 3.5, 90.0),
    (3, 5, 3, '2024-08-26', 'A', 4.0, 98.0),
    (3, 6, 3, '2024-08-26', 'A', 3.8, 96.0),
    (4, 8, 3, '2024-08-26', 'B+', 3.3, 85.0),
    (4, 9, 3, '2024-08-26', 'A-', 3.7, 92.0)
ON CONFLICT DO NOTHING;

-- Add some class sessions
INSERT INTO raw_edu.class_sessions (course_id, faculty_id, semester_id, session_date, session_time, attendance_count) VALUES
    (1, 1, 3, '2024-08-26', '10:00:00', 25),
    (2, 1, 3, '2024-08-26', '14:00:00', 20),
    (5, 3, 3, '2024-08-26', '09:00:00', 30),
    (6, 3, 3, '2024-08-26', '11:00:00', 22),
    (8, 4, 3, '2024-08-26', '13:00:00', 35),
    (9, 4, 3, '2024-08-26', '15:00:00', 28)
ON CONFLICT DO NOTHING;

-- Add sample assignments
INSERT INTO raw_edu.assignments (course_id, semester_id, assignment_name, assignment_type, due_date, max_points, weight_percentage) VALUES
    (1, 3, 'Homework 1: Basic Programming', 'homework', '2024-09-15', 100.00, 15.0),
    (1, 3, 'Midterm Exam', 'exam', '2024-10-15', 200.00, 30.0),
    (1, 3, 'Final Project', 'project', '2024-12-10', 300.00, 40.0),
    (2, 3, 'Algorithm Analysis', 'homework', '2024-09-20', 150.00, 20.0),
    (2, 3, 'Data Structure Implementation', 'project', '2024-11-15', 250.00, 35.0),
    (5, 3, 'Calculus Problem Set 1', 'homework', '2024-09-10', 80.00, 10.0),
    (5, 3, 'Calculus Midterm', 'exam', '2024-10-20', 150.00, 25.0),
    (6, 3, 'Linear Algebra Assignments', 'homework', '2024-09-25', 120.00, 20.0),
    (8, 3, 'Business Case Study', 'case_study', '2024-10-05', 100.00, 25.0),
    (9, 3, 'Marketing Campaign Project', 'project', '2024-11-20', 200.00, 40.0)
ON CONFLICT DO NOTHING;

-- Add sample assignment submissions
INSERT INTO raw_edu.assignment_submissions (assignment_id, student_id, submission_date, score, late_submission, feedback) VALUES
    (1, 1, '2024-09-14 15:30:00', 92.00, false, 'Excellent work on basic programming concepts'),
    (1, 2, '2024-09-16 10:20:00', 78.00, true, 'Good effort, submitted late'),
    (2, 1, '2024-10-14 14:00:00', 185.00, false, 'Outstanding performance on midterm'),
    (2, 2, '2024-10-15 14:00:00', 165.00, false, 'Solid understanding of concepts'),
    (4, 2, '2024-09-19 16:45:00', 140.00, false, 'Great analysis of algorithms'),
    (6, 3, '2024-09-09 12:00:00', 75.00, false, 'Good work on calculus problems'),
    (7, 3, '2024-10-19 13:30:00', 138.00, false, 'Strong performance on midterm'),
    (8, 3, '2024-09-24 18:20:00', 110.00, false, 'Excellent linear algebra work'),
    (9, 4, '2024-10-04 11:15:00', 88.00, false, 'Insightful business case analysis'),
    (10, 4, '2024-11-19 22:30:00', 175.00, false, 'Creative marketing campaign')
ON CONFLICT DO NOTHING;

-- Add sample financial aid data
INSERT INTO raw_edu.financial_aid (student_id, aid_type, amount, academic_year, disbursement_date) VALUES
    (1, 'Merit Scholarship', 5000.00, '2024-2025', '2024-08-15'),
    (2, 'Need-based Grant', 3500.00, '2024-2025', '2024-08-15'),
    (3, 'Academic Excellence Award', 7500.00, '2024-2025', '2024-08-15'),
    (4, 'Work Study', 2000.00, '2024-2025', '2024-09-01'),
    (5, 'Merit Scholarship', 4000.00, '2023-2024', '2023-08-15'),
    (6, 'Engineering Excellence Grant', 6000.00, '2024-2025', '2024-08-15'),
    (7, 'Need-based Grant', 2500.00, '2024-2025', '2024-08-15'),
    (8, 'Dean''s List Scholarship', 3000.00, '2024-2025', '2024-08-15')
ON CONFLICT DO NOTHING;

-- Add sample tuition payment data
INSERT INTO raw_edu.tuition_payments (student_id, semester_id, amount, payment_date, payment_method, late_fee) VALUES
    (1, 3, 12500.00, '2024-08-20', 'Credit Card', 0.00),
    (2, 3, 12500.00, '2024-08-25', 'Bank Transfer', 0.00),
    (3, 3, 12500.00, '2024-08-18', 'Check', 0.00),
    (4, 3, 12500.00, '2024-09-05', 'Credit Card', 150.00),
    (6, 3, 15000.00, '2024-08-22', 'Bank Transfer', 0.00),
    (7, 3, 12500.00, '2024-08-30', 'Credit Card', 0.00),
    (8, 3, 12500.00, '2024-08-19', 'Check', 0.00)
ON CONFLICT DO NOTHING;

-- Add more enrollments for sufficient data per course
INSERT INTO raw_edu.enrollments (student_id, course_id, semester_id, enrollment_date, grade, grade_points, attendance_percentage, enrollment_status, completion_date) VALUES
    (5, 1, 2, '2024-01-15', 'A-', 3.7, 93.0, 'Completed', '2024-05-10'),
    (6, 1, 2, '2024-01-15', 'B', 3.0, 87.0, 'Completed', '2024-05-10'),
    (7, 1, 2, '2024-01-15', 'C+', 2.3, 78.0, 'Completed', '2024-05-10'),
    (8, 1, 2, '2024-01-15', 'B+', 3.3, 91.0, 'Completed', '2024-05-10'),
    (3, 2, 3, '2024-08-26', 'A', 4.0, 95.0, 'Completed', '2024-12-13'),
    (4, 2, 3, '2024-08-26', 'B-', 2.7, 84.0, 'Completed', '2024-12-13'),
    (5, 2, 2, '2024-01-15', 'B+', 3.3, 89.0, 'Completed', '2024-05-10'),
    (6, 2, 2, '2024-01-15', 'A-', 3.7, 92.0, 'Completed', '2024-05-10'),
    (1, 6, 3, '2024-08-26', 'B+', 3.3, 88.0, 'Completed', '2024-12-13'),
    (2, 6, 3, '2024-08-26', 'A', 4.0, 96.0, 'Completed', '2024-12-13'),
    (4, 6, 3, '2024-08-26', 'B', 3.0, 85.0, 'Completed', '2024-12-13'),
    (5, 8, 2, '2024-01-15', 'B+', 3.3, 90.0, 'Completed', '2024-05-10'),
    (6, 8, 2, '2024-01-15', 'A', 4.0, 94.0, 'Completed', '2024-05-10'),
    (7, 8, 2, '2024-01-15', 'B', 3.0, 86.0, 'Completed', '2024-05-10'),
    (1, 9, 3, '2024-08-26', 'A-', 3.7, 91.0, 'Completed', '2024-12-13'),
    (2, 9, 3, '2024-08-26', 'B+', 3.3, 88.0, 'Completed', '2024-12-13'),
    (3, 9, 3, '2024-08-26', 'A', 4.0, 97.0, 'Completed', '2024-12-13')
ON CONFLICT DO NOTHING;

-- Add enrollment_status column and update completion dates for existing enrollments
ALTER TABLE raw_edu.enrollments ADD COLUMN IF NOT EXISTS enrollment_status TEXT DEFAULT 'Completed';

-- Update completion dates for existing enrollments
UPDATE raw_edu.enrollments 
SET completion_date = CASE 
    WHEN semester_id = 1 THEN DATE '2023-12-15'  -- Fall 2023
    WHEN semester_id = 2 THEN DATE '2024-05-10'  -- Spring 2024  
    WHEN semester_id = 3 THEN DATE '2024-12-13'  -- Fall 2024
    WHEN semester_id = 4 THEN DATE '2025-05-08'  -- Spring 2025
    ELSE DATE '2024-05-10'
END
WHERE completion_date IS NULL AND grade IS NOT NULL AND grade NOT IN ('W', 'I');

-- Grant permissions on Superset database
\c superset_db;
GRANT ALL PRIVILEGES ON DATABASE superset_db TO dbt_user;
GRANT ALL PRIVILEGES ON SCHEMA public TO dbt_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO dbt_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO dbt_user;