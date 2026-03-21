const API_TOKEN = "1fffcdec3d409880b868e13e494f75da:ca8f3aa9e748cee652e3278188ea7538";
const API_BASE = "https://api.gurufocus.com/public/user/" + API_TOKEN;

const TICKERS = [
  "TSLA", "MSTR", "NVDA", "META", "GOOGL", "AMZN", "MSFT", "AMD", "TSM",
  "PLTR", "CRWD", "HOOD", "COIN", "MELI", "SHOP"
];

function onOpen() {
  var ui = SpreadsheetApp.getUi();
  ui.createMenu('Focus List')
    .addItem('Refresh Data', 'refreshAllData')
    .addItem('Setup Sheet', 'setupSheet')
    .addToUi();
}

function setupSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName("Focus List");
  if (!sheet) {
    sheet = ss.insertSheet("Focus List");
  }
  sheet.clear();
  
  sheet.getRange("A1").setValue("Focus List").setFontSize(14).setFontWeight("bold");
  
  var headers = ["Ticker", "Company", "Price", "GF Value", "Prem/Disc", "GF Score", "Altman Z", "Piotroski F", "PE", "52w High", "% from High", "Signal", "Updated"];
  sheet.getRange(3, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(3, 1, 1, headers.length).setBackground("#1F4E79").setFontColor("white").setFontWeight("bold");
  
  for (var i = 0; i < TICKERS.length; i++) {
    sheet.getRange(4 + i, 1).setValue(TICKERS[i]);
  }
  
  sheet.setFrozenRows(3);
  SpreadsheetApp.getUi().alert("Setup complete! Now click Focus List > Refresh Data");
}

function refreshAllData() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName("Focus List");
  
  if (!sheet) {
    setupSheet();
    sheet = ss.getSheetByName("Focus List");
  }
  
  for (var i = 0; i < TICKERS.length; i++) {
    var ticker = TICKERS[i];
    var row = 4 + i;
    
    try {
      var url = API_BASE + "/stock/" + ticker + "/summary";
      var response = UrlFetchApp.fetch(url, {muteHttpExceptions: true});
      var data = JSON.parse(response.getContentText());
      
      var company_data = data.summary.company_data;
      
      var companyName = company_data.company || "";
      var price = parseFloat(company_data.price) || 0;
      var gfValue = parseFloat(company_data.gf_value) || 0;
      var p2gfValue = parseFloat(company_data.p2gf_value) || 0;
      var premDisc = p2gfValue > 0 ? (1 - p2gfValue) * -1 : 0;
      var gfScore = parseFloat(company_data.gf_score) || 0;
      var altmanZ = parseFloat(company_data.zscore) || 0;
      var piotroski = parseFloat(company_data.fscore) || 0;
      var pe = parseFloat(company_data.pettm) || 0;
      var high52 = parseFloat(company_data.price52whigh) || 0;
      var pctFromHigh = high52 > 0 ? (price - high52) / high52 : 0;
      
      var signal = 0;
      if (gfScore >= 80) signal++;
      if (p2gfValue < 0.85) signal++;
      if (pctFromHigh > -0.15) signal++;
      if (piotroski >= 6) signal++;
      
      var rowData = [ticker, companyName, price, gfValue, premDisc, gfScore, altmanZ, piotroski, pe, high52, pctFromHigh, signal, new Date()];
      sheet.getRange(row, 1, 1, rowData.length).setValues([rowData]);
      
      sheet.getRange(row, 3).setNumberFormat("$#,##0.00");
      sheet.getRange(row, 4).setNumberFormat("$#,##0.00");
      sheet.getRange(row, 5).setNumberFormat("0.0%");
      sheet.getRange(row, 10).setNumberFormat("$#,##0.00");
      sheet.getRange(row, 11).setNumberFormat("0.0%");
      
      if (signal >= 3) {
        sheet.getRange(row, 12).setBackground("#90EE90");
      } else if (signal >= 2) {
        sheet.getRange(row, 12).setBackground("#FFFFE0");
      } else {
        sheet.getRange(row, 12).setBackground("#FFFFFF");
      }
      
      Utilities.sleep(500);
      
    } catch (e) {
      sheet.getRange(row, 2).setValue("Error: " + e.message);
    }
  }
  
  SpreadsheetApp.getUi().alert("Data refresh complete!");
}
