const API_TOKEN = "1fffcdec3d409880b868e13e494f75da:ca8f3aa9e748cee652e3278188ea7538";
const API_BASE = "https://api.gurufocus.com/public/user/" + API_TOKEN;

const TICKERS = [
  "TSLA", "MSTR", "NVDA", "META", "GOOGL", "AMZN", "MSFT", "AMD", "TSM",
  "PLTR", "CRWD", "HOOD", "COIN", "MELI", "SHOP"
];

// ADD EMAIL ADDRESSES HERE (comma separated)
const EMAIL_ADDRESSES = "email1@gmail.com, email2@gmail.com";

function onOpen() {
  var ui = SpreadsheetApp.getUi();
  ui.createMenu('Focus List')
    .addItem('Refresh Data', 'refreshAllData')
    .addItem('Setup Sheet', 'setupSheet')
    .addItem('Send Email Now', 'refreshAndEmail')
    .addItem('Enable Daily Email (8am ET)', 'setupDailyTrigger')
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
  
  var headers = ["Ticker", "Company", "Price", "GF Value", "Prem/Disc", "GF Score", "Altman Z", "Piotroski F", "Momentum", "Sales Growth Est", "52w High", "% from High", "Signal", "Updated"];
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
      var momentum = parseFloat(company_data.rank_momentum) || 0;
      var salesGrowth = parseFloat(company_data.total_rvn_growth_5y_est) || parseFloat(company_data.rvn_growth_5y) || 0;
      var high52 = parseFloat(company_data.price52whigh) || 0;
      var pctFromHigh = high52 > 0 ? (price - high52) / high52 : 0;
      
      var signal = 0;
      if (gfScore >= 80) signal++;
      if (p2gfValue < 0.85) signal++;
      if (pctFromHigh > -0.15) signal++;
      if (piotroski >= 6) signal++;
      
      var rowData = [ticker, companyName, price, gfValue, premDisc, gfScore, altmanZ, piotroski, momentum, salesGrowth / 100, high52, pctFromHigh, signal, new Date()];
      sheet.getRange(row, 1, 1, rowData.length).setValues([rowData]);
      
      sheet.getRange(row, 3).setNumberFormat("$#,##0.00");
      sheet.getRange(row, 4).setNumberFormat("$#,##0.00");
      sheet.getRange(row, 5).setNumberFormat("0.0%");
      sheet.getRange(row, 10).setNumberFormat("0.0%");
      sheet.getRange(row, 11).setNumberFormat("$#,##0.00");
      sheet.getRange(row, 12).setNumberFormat("0.0%");
      
      if (signal >= 3) {
        sheet.getRange(row, 13).setBackground("#90EE90");
      } else if (signal >= 2) {
        sheet.getRange(row, 13).setBackground("#FFFFE0");
      } else {
        sheet.getRange(row, 13).setBackground("#FFFFFF");
      }
      
      Utilities.sleep(500);
      
    } catch (e) {
      sheet.getRange(row, 2).setValue("Error: " + e.message);
    }
  }
}

function setupDailyTrigger() {
  removeTriggers();
  
  // 8am ET = 13:00 UTC (or 12:00 UTC during daylight saving)
  ScriptApp.newTrigger('refreshAndEmail')
    .timeBased()
    .everyDays(1)
    .atHour(13)
    .inTimezone("America/New_York")
    .create();
  
  SpreadsheetApp.getUi().alert("Daily email enabled! You'll receive updates at 8am ET.");
}

function removeTriggers() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    ScriptApp.deleteTrigger(triggers[i]);
  }
}

function refreshAndEmail() {
  refreshAllData();
  sendDailyEmail();
}

function sendDailyEmail() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName("Focus List");
  
  if (!sheet) {
    return;
  }
  
  var data = sheet.getRange(4, 1, TICKERS.length, 14).getValues();
  
  // Priority order: TSLA, MSTR, NVDA first, then rest by signal
  var priority = {"TSLA": 1, "MSTR": 2, "NVDA": 3};
  data.sort(function(a, b) {
    var aPriority = priority[a[0]] || 100;
    var bPriority = priority[b[0]] || 100;
    if (aPriority !== bPriority) return aPriority - bPriority;
    return b[12] - a[12];
  });
  
  var today = new Date().toLocaleDateString('en-US', {weekday: 'short', month: 'short', day: 'numeric'});
  
  var html = `
  <div style="font-family: -apple-system, Arial, sans-serif; max-width: 400px; margin: 0 auto; padding: 10px;">
    <h2 style="color: #1F4E79; margin-bottom: 5px; font-size: 18px;">📊 Focus List</h2>
    <p style="color: #666; margin-top: 0; font-size: 12px;">${today}</p>
  `;
  
  for (var i = 0; i < data.length; i++) {
    var ticker = data[i][0];
    var price = data[i][2];
    var premDisc = data[i][4];
    var piotroski = data[i][7];
    var momentum = data[i][8];
    var salesGrowth = data[i][9] * 100;
    
    var premDiscColor = premDisc < 0 ? "#22c55e" : "#ef4444";
    var premDiscText = premDisc < 0 ? Math.abs(premDisc * 100).toFixed(0) + "% under" : (premDisc * 100).toFixed(0) + "% over";
    
    var momentumColor = momentum >= 7 ? "#22c55e" : momentum >= 4 ? "#eab308" : "#ef4444";
    var piotColor = piotroski >= 7 ? "#22c55e" : piotroski >= 5 ? "#eab308" : "#ef4444";
    var growthColor = salesGrowth >= 20 ? "#22c55e" : salesGrowth >= 10 ? "#eab308" : "#ef4444";
    
    var isTop3 = priority[ticker] ? true : false;
    var cardBg = isTop3 ? "#f8fafc" : "#ffffff";
    var borderLeft = isTop3 ? "border-left: 3px solid #1F4E79;" : "";
    
    html += `
    <div style="background: ${cardBg}; ${borderLeft} padding: 10px; margin-bottom: 6px; border-radius: 6px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
        <span style="font-weight: bold; font-size: 15px;">${ticker}</span>
        <div>
          <span style="font-size: 15px; font-weight: 600;">$${price.toFixed(2)}</span>
          <span style="color: ${premDiscColor}; font-size: 12px; margin-left: 6px;">${premDiscText}</span>
        </div>
      </div>
      
      <div style="display: flex; gap: 8px;">
        <span style="background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 11px; color: ${growthColor};">
          📈 ${salesGrowth.toFixed(0)}%
        </span>
        <span style="background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 11px; color: ${momentumColor};">
          ⚡ ${momentum}/10
        </span>
        <span style="background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 11px; color: ${piotColor};">
          💪 ${piotroski}/9
        </span>
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
    to: EMAIL_ADDRESSES,
    subject: "📊 Focus List - " + today,
    htmlBody: html
  });
}
