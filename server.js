const express = require("express");
const bodyParser = require("body-parser");
const mysql = require("mysql");
const cors = require("cors");
const multer = require("multer");
const path = require("path");
const fs = require("fs");
const moment = require('moment');

const app = express();
const port = process.env.PORT || 8080;

const uploadDir = "uploads";
if (!fs.existsSync(uploadDir)) {
  fs.mkdirSync(uploadDir);
}


app.use(cors());

app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));


const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, uploadDir);
  },
  filename: (req, file, cb) => {
    cb(null, `${Date.now()}-${file.originalname}`);
  },
});

const upload = multer({ storage });

// MySQL connection configuration
const db = mysql.createConnection({
  host: "localhost",
  user: "root",
  password: "",
  database: "foreach",
});

db.connect((err) => {
  if (err) {
    console.error("Error connecting to MySQL:", err);
    throw err;
  }
  console.log("MySQL connected...");
});
app.use('/uploads', express.static(path.join(__dirname, 'uploads')));



app.post("/submit/partner", upload.single("file"), (req, res) => {
  const {
    detail1,
    detail2,
    category,
    detail3,
    detail4,
    socialfb,
    socialweb,
    socialinsta,
  } = req.body;
  const file_part = req.file ? req.file.filename : null;

  const newPartner = {
    name_part: detail1,
    category_part: category,
    file_part,
    des_part: detail2,
    address_part: detail3,
    phone_part: detail4,
    web_part: socialweb,
    fac_part: socialfb,
    insta_part: socialinsta,
  };

  const query = "INSERT INTO partners SET ?";

  db.query(query, newPartner, (err, result) => {
    if (err) {
      console.error("Error saving data:", err);
      res.status(200).send("Data saved successfully");
    }
  });
});

app.post("/submit/event", upload.single("file"), (req, res) => {
  const { desc1, desc2, desc3, desc4, area1, area2, area3, check } = req.body;
  const event_file = req.file ? req.file.filename : null;

  const event_date_de = moment(desc2).format('DD-MM-YYYY');
  const event_date_a = moment(desc3).format('DD-MM-YYYY');
  const newEvent = {
    event_name: desc1,
    event_date_de: desc2,
    event_date_a: desc3,
    event_file,
    event_location: desc4,
    event_ob: area1 ,
    event_scd: area2 ,
    event_det: area3 ,
    event_check: check? true:false,
  };

  

  const query = "INSERT INTO events SET ?";

  db.query(query, newEvent, (err, result) => {
    if (err) {
      console.error("Error saving data:", err);
      return res.status(500).send("Error saving data");
    }
    res.status(200).send("Data saved successfully");
  });
});







app.post("/submit/partner", upload.single("file"), (req, res) => {
  const {
    detail1,
    detail2,
    category,
    detail3,
    detail4,
    socialfb,
    socialweb,
    socialinsta,
  } = req.body;
  const file_part = req.file ? req.file.filename : null;

  const newPartner = {
    name_part: detail1,
    category_part: category,
    file_part,
    des_part: detail2,
    address_part: detail3,
    phone_part: detail4,
    web_part: socialweb,
    fac_part: socialfb,
    insta_part: socialinsta,
  };

  const query = "INSERT INTO partners SET ?";

  db.query(query, newPartner, (err, result) => {
    if (err) {
      console.error("Error saving data:", err);
      res.status(200).send("Data saved successfully");
    }
  });
});

app.post('/submit/jobs', (req, res) => {
  const { jbs1, jbs2, jbs3, filed1, filed2, filed3, jobType } = req.body;

  const newJob = {
    title_jobs: jbs1,
    departement_jobs: jbs2,
    location_jobs: jbs3,
    description_jobs: filed1,
    benefits_jobs: filed2,
    req_jobs: filed3,
  };

  if (jobType === 'Internal') {
    newJob.internal_jobs = true;
    newJob.external_jobs = false;
    newJob.refferal_jobs = false;
  } else if (jobType === 'External') {
    newJob.internal_jobs = false;
    newJob.external_jobs = true;
    newJob.refferal_jobs = false;
  } else if (jobType === 'Referral') {
    newJob.internal_jobs = false;
    newJob.external_jobs = false;
    newJob.refferal_jobs = true;
  }

  const query = 'INSERT INTO jobs SET ?';

  db.query(query, newJob, (err, result) => {
    if (err) {
      console.error('Error saving data:', err);
      return res.status(500).send('Error saving data');
    }
    res.status(200).send('Data saved successfully');
  });
});


app.get("/jobs", (req, res) => {
  const query = "SELECT * FROM partners";

  db.query(query, (err, results) => {
    if (err) {
      console.error("Error fetching partners data:", err);
      return res.status(500).send("Error fetching partners data");
    }
    res.json(results);
  });
});







app.get("/partners", (req, res) => {
  const query = "SELECT * FROM partners";

  db.query(query, (err, results) => {
    if (err) {
      console.error("Error fetching partners data:", err);
      return res.status(500).send("Error fetching partners data");
    }
    res.json(results);
  });
});

app.get("/events", (req, res) => {
  const query = "SELECT * FROM events";

  db.query(query, (err, results) => {
    if (err) {
      console.error("Error fetching events data:", err);
      return res.status(500).send("Error fetching events data");
    }
    res.json(results);
  });
});

app.delete('/partners/:id_part', function(req, res){
  var sql      = 'DELETE FROM partners WHERE id_part = ?';
  var id_movie = [req.params.id_part];
  con.query(sql, id_part, function(err){
      if(err){
          res.json({"Error": true, "Message": "Error execute sql"});
      } else {
          res.json({"Error": false, "Message": "Success"});
      }
  });
});
app.use("/uploads", express.static(path.join(__dirname, "uploads")));

app.listen(port, () => {
  console.log(`Server started on port ${port}`);
});
