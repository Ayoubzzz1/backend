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

// Ensure the uploads directory exists
const uploadDir = "uploads";
if (!fs.existsSync(uploadDir)) {
  fs.mkdirSync(uploadDir);
}

// CORS configuration
app.use(cors());

// Body-parser configuration
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));

// Multer configuration for file upload
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


// Route for form submission with file upload for partners
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

// Route for form submission with file upload for events
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

// Route for form submission with file upload for events
app.post("/submit/jobs", (req, res) => {
  const { jbs1, jbs2, jbs3, filed1, filed2, filed3, jobType } = req.body;
  const event_file = req.file ? req.file.filename : null;

  // Determine the job type based on the radio button selection
  let jobTypeValue = null;
  if (jobType === 'internal') {
    jobTypeValue = 'internal_jobs';
  } else if (jobType === 'external') {
    jobTypeValue = 'external_jobs';
  } else if (jobType === 'referal') {
    jobTypeValue = 'referal_jobs';
  }

  const newJob = {
    title_jobs: jbs1,
    departement_jobs: jbs2,
    location_jobs: jbs3,
    description_jobs: filed1,
    benefits_jobs: filed2,
    job_type: jobTypeValue, // Updated to reflect job type
  };

  const query = "INSERT INTO jobs SET ?";

  db.query(query, newJob, (err, result) => {
    if (err) {
      console.error("Error saving data:", err);
      return res.status(500).send("Error saving data");
    }
    res.status(200).send("Data saved successfully");
  });
});








// Route for fetching partner data
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


// app.put("/api/partners/:id", upload.single("file"), (req, res) => {
//   const id = req.params.id;
//   const { name, category, address, phone, facebook, website, instagram } =
//     req.body;
//   const file = req.file ? req.file.filename : null;

//   let updateQuery = `
//       UPDATE partners
//       SET name_part = ?, category_part = ?, address_part = ?, phone_part = ?, fac_part = ?, web_part = ?, insta_part = ?
//       ${file ? ", file_part = ?" : ""}
//       WHERE id_part = ?
//     `;

//   let params = [name, category, address, phone, facebook, website, instagram];
//   if (file) {
//     params.push(file);
//   }
//   params.push(id);

//   // Execute the query
//   db.query(updateQuery, params, (err, result) => {
//     if (err) {
//       console.error("Error updating partner:", err);
//       if (err.code === "ER_DUP_ENTRY") {
//         return res.status(400).send("A partner with this name already exists.");
//       }
//       return res.status(500).send("Error updating partner.");
//     }
//     res.send("Partner updated successfully.");
//   });
// });

// Serve static files for uploaded content
app.use("/uploads", express.static(path.join(__dirname, "uploads")));

app.listen(port, () => {
  console.log(`Server started on port ${port}`);
});
