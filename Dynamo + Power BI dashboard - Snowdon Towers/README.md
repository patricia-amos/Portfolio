# Revit BIM Data Automation & Analytics Pipeline 

## 🏢 Dataset & Project Baseline
To ensure complete compliance with data privacy laws and intellectual property rights, this pipeline was developed and stress-tested using **Autodesk's Industry-Standard Revit Sample Architecture Project** (*Snowdon Towers Sample Architectural.rvt*). 

Using a widely recognized open baseline allows peers and recruiters to easily reproduce the entire pipeline locally.

## 🛠️ Tools & Technologies

- **Autodesk Revit 2025** — BIM model and source data
- **Dynamo v.3.3.0  ** — Automated Revit data extraction
- **Power Query** — Data cleaning and transformation
- **Power BI** — Data modeling and dashboard visualization
- **DAX** — Calculations and KPI measures
- **GitHub** — Project documentation and version control


## ⚡ 1. Data Extraction with Dynamo

There are 3 data sets that were extracted from the Revit file through dynamo. 

The first one is the ModelParameters.csv. This dynamo script extracts the parameters namely element ID, type, name, category, level, area, volume, length, mark, comments, phase created, and workset from the model with initial data cleaning, list arrangements, and  data export into a csv file. 

### Dynamo Graph
![Dynamo Graph for ModelParameters Data Set](images/ModelParameters_Dynamo.png)

The graph started with a python script that searches the Revit document and returns model elements that have actual 3D solid geometry, while excluding things such as element types, annotations, views, sheets, rooms, spaces, areas, and other non-solid/model data. 

Initially, I wanted to use nodes for this but I was limited with options because the existing nodes that were in dynamo required me to specify per category to be able to extract its corresponding elements which would be inefficient since I wanted to extract ALL placed model elements and not just elements from specific categories. Using a python script was the best option for this case as it can collect all model elements without the need to specify. 




## 🧼 2. Data Cleaning with Power Query

### Before Cleaning

### After Cleaning

## 📊 3. Power BI Dashboard

### Dashboard Design

## 🚀 4. How to Reproduce the Project

