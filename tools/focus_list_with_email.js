const API_TOKEN = "1fffcdec3d409880b868e13e494f75da:ca8f3aa9e748cee652e3278188ea7538";
const API_BASE = "https://api.gurufocus.com/public/user/" + API_TOKEN;

const TICKERS = [
  "TSLA", "MSTR", "NVDA", "META", "GOOGL", "AMZN", "MSFT", "AMD", "TSM",
  "PLTR", "CRWD", "HOOD", "COIN", "MELI", "SHOP"
];

// SET YOUR EMAIL HERE
const EMAIL_ADDRESS = "YOUR_EMAIL@gmail.com";

function onOpen() {
  var ui = SpreadsheetApp.getUi();
  ui.createMenu('Focus List')
    .addItem('Refresh Data', 'refreshAllData')
    .addItem('Setup Sheet', 'setupSheet')
    .addItem('Send Email Now', 'sendDailyEmail')
    .addItem('Enable Daily Email (7am)', 'setupDailyTrigger')
    .addItem('Disable Daily Email', 'removeTriggers')
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
}

function setupDailyTrigger() {
  removeTriggers();
  
  ScriptApp.newTrigger('dailyRefreshAndEmail')
    .timeBased()
    .everyDays(1)
    .atHour(7)
    .create();
  
  SpreadsheetApp.getUi().alert("Daily email enabled! You'll receive updates at 7am.");
}

function removeTriggers() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    ScriptApp.deleteTrigger(triggers[i]);
  }
}

function dailyRefreshAndEmail() {
  refreshAllData();
  sendDailyEmail();
}

function sendDailyEmail() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName("Focus List");
  
  if (!sheet) {
    return;
  }
  
  var data = sheet.getRange(4, 1, TICKERS.length, 13).getValues();
  
  // Sort by signal strength (descending)
  data.sort(function(a, b) {
    return b[11] - a[11];
  });
  
  var today = new Date().toLocaleDateString('en-US', {weekday: 'short', month: 'short', day: 'numeric'});
  
  // Build mobile-friendly HTML email
  var html = `
  <div style="font-family: -apple-system, Arial, sans-serif; max-width: 400px; margin: 0 auto; padding: 10px;">
    <h2 style="color: #1F4E79; margin-bottom: 5px; font-size: 18px;">📊 Focus List</h2>
    <p style="color: #666; margin-top: 0; font-size: 12px;">${today}</p>
    
    <div style="background: #f0f7ff; padding: 10px; border-radius: 8px; margin-bottom: 15px;">
      <strong style="font-size: 13px;">🔥 Top Signals</strong>
    </div>
  `;
  
  for (var i = 0; i < data.length; i++) {
    var ticker = data[i][0];
    var company = data[i][1];
    var price = data[i][2];
    var gfValue = data[i][3];
    var premDisc = data[i][4];
    var gfScore = data[i][5];
    var piotroski = data[i][7];
    var pctFromHigh = data[i][10];
    var signal = data[i][11];
    
    var signalColor = signal >= 3 ? "#22c55e" : signal >= 2 ? "#eab308" : "#94a3b8";
    var premDiscColor = premDisc < 0 ? "#22c55e" : "#ef4444";
    var premDiscText = premDisc < 0 ? (Math.abs(premDisc) * 100).toFixed(0) + "% under" : (premDisc * 100).toFixed(0) + "% over";
    
    html += `
    <div style="border-bottom: 1px solid #eee; padding: 12px 0;">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
          <span style="font-weight: bold; font-size: 15px;">${ticker}</span>
          <span style="background: ${signalColor}; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px; margin-left: 5px;">${signal}/4</span>
        </div>
        <span style="font-size: 15px; font-weight: 500;">$${price.toFixed(2)}</span>
      </div>
      <div style="color: #666; font-size: 12px; margin-top: 4px;">
        GF Value: $${gfValue.toFixed(0)} · <span style="color: ${premDiscColor};">${premDiscText}</span>
      </div>
      <div style="color: #888; font-size: 11px; margin-top: 2px;">
        GF Score: ${gfScore} · Piotroski: ${piotroski} · ${(pctFromHigh * 100).toFixed(0)}% from high
      </div>
    </div>
    `;
  }
  
  html += `
    <p style="color: #999; font-size: 10px; margin-top: 15px; text-align: center;">
      <a href="${ss.getUrl()}" style="color: #1F4E79;">Open Full Sheet</a>
    </p>
  </div>
  `;
  
  MailApp.sendEmail({
    to: EMAIL_ADDRESS,
    subject: "📊 Focus List - " + today,
    htmlBody: html
  });
}
