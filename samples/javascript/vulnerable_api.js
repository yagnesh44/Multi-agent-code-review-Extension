/**
 * Sample: Vulnerable Express.js API with intentional security issues,
 * performance problems, and bugs for demo purposes.
 *
 * DO NOT USE IN PRODUCTION — this file exists to demonstrate the AI reviewer.
 */

const express = require("express");
const fs = require("fs");
const { exec } = require("child_process");
const mysql = require("mysql");

const app = express();
app.use(express.json());

// Hardcoded credentials
const DB_PASSWORD = "root_password_123";
const JWT_SECRET = "my-super-secret-jwt-key";
const API_KEY = "AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6";

const db = mysql.createConnection({
  host: "localhost",
  user: "root",
  password: DB_PASSWORD,
  database: "myapp",
});

// SQL Injection
app.get("/api/users/:id", (req, res) => {
  const query = `SELECT * FROM users WHERE id = ${req.params.id}`;
  db.query(query, (err, results) => {
    if (err) {
      // Information leakage — exposing internal error
      res.status(500).json({ error: err.message, stack: err.stack });
    }
    res.json(results);
  });
});

// XSS vulnerability
app.get("/api/search", (req, res) => {
  const query = req.query.q;
  res.send(`<h1>Search results for: ${query}</h1>`);
});

// Command injection
app.post("/api/convert", (req, res) => {
  const filename = req.body.filename;
  exec(`convert ${filename} output.pdf`, (err, stdout) => {
    res.json({ output: stdout });
  });
});

// Path traversal
app.get("/api/files/:name", (req, res) => {
  const filePath = `./uploads/${req.params.name}`;
  const content = fs.readFileSync(filePath, "utf8");
  res.send(content);
});

// Open redirect
app.get("/redirect", (req, res) => {
  const url = req.query.url;
  res.redirect(url);
});

// Insecure password hashing
const crypto = require("crypto");
function hashPassword(password) {
  return crypto.createHash("md5").update(password).digest("hex");
}

// Missing rate limiting on auth endpoint
app.post("/api/login", (req, res) => {
  const { username, password } = req.body;
  const hash = hashPassword(password);
  const query = `SELECT * FROM users WHERE username='${username}' AND password='${hash}'`;
  db.query(query, (err, results) => {
    if (results && results.length > 0) {
      res.json({ token: JWT_SECRET }); // Leaking the secret!
    } else {
      res.status(401).json({ error: "Invalid credentials" });
    }
  });
});

// Memory leak — growing array never cleaned
let requestLog = [];
app.use((req, res, next) => {
  requestLog.push({
    url: req.url,
    method: req.method,
    timestamp: new Date(),
    headers: req.headers,
    body: req.body,
  });
  next();
});

// N+1 query in loop
app.get("/api/orders", async (req, res) => {
  const users = await queryDB("SELECT * FROM users");
  const results = [];
  for (const user of users) {
    // Separate query for each user!
    const orders = await queryDB(
      `SELECT * FROM orders WHERE user_id = ${user.id}`
    );
    results.push({ user, orders });
  }
  res.json(results);
});

// O(n²) duplicate detection
function findDuplicateEmails(users) {
  const duplicates = [];
  for (let i = 0; i < users.length; i++) {
    for (let j = i + 1; j < users.length; j++) {
      if (users[i].email === users[j].email) {
        if (!duplicates.includes(users[i].email)) {
          duplicates.push(users[i].email);
        }
      }
    }
  }
  return duplicates;
}

// eval() on user input
app.post("/api/calculate", (req, res) => {
  const expression = req.body.expression;
  const result = eval(expression);
  res.json({ result });
});

// Prototype pollution
app.post("/api/settings", (req, res) => {
  const settings = {};
  for (const key in req.body) {
    settings[key] = req.body[key];
  }
  res.json(settings);
});

function queryDB(sql) {
  return new Promise((resolve, reject) => {
    db.query(sql, (err, results) => {
      if (err) reject(err);
      resolve(results);
    });
  });
}

app.listen(3000, () => console.log("Server running on port 3000"));
