async function loadCSV() {
    const response = await fetch("./daily_returns.csv");
    const text = await response.text();
    const lines = text.trim().split("\n");
    const headers = lines[0].split(",");
    return lines.slice(1).map(row => {
        const cols = row.split(",");
        const obj = {};
        headers.forEach((h, i) => { obj[h] = cols[i]; });
        return obj;
    });
}
function parseDate(str){ return new Date(str); }
function getCurrentMonthData(data){
    const now=new Date();
    return data.filter(d=>{const dt=parseDate(d.fetch_date);return dt.getFullYear()==now.getFullYear()&&dt.getMonth()==now.getMonth();});
}
function chartLine(ctx,labels,datasets){
    return new Chart(ctx,{type:"line",data:{labels:labels,datasets:datasets},
        options:{responsive:true,plugins:{legend:{labels:{color:"#fff"}}},
        scales:{x:{ticks:{color:"#fff"}},y:{ticks:{color:"#fff"}}}}});
}
async function main(){
    const raw=await loadCSV();
    if(raw.length===0)return;
    document.getElementById("last_update").innerText=raw[raw.length-1].fetch_date;
    const monthData=getCurrentMonthData(raw);
    const FUNDS=[{key:"NASDAQ100",label:"NASDAQ100"},{key:"VTI",label:"VTI"},{key:"SP500",label:"S&P500"},{key:"NASDAQ100_L",label:"NASDAQ100(レバ)"}];
    const labels=monthData.map(d=>d.fetch_date.split(" ")[0]);
    const datasetsNAV=[],datasetsRate=[],datasetsDiff=[];
    FUNDS.forEach(f=>{
        const navList=monthData.map(d=>Number(d[f.key]));
        const base=navList[0];
        const rate=navList.map(v=>((v/base)-1)*100);
        const diff=navList.map(v=>v-base);
        const color=`hsl(${Math.random()*360},70%,60%)`;
        datasetsNAV.push({label:f.label,borderColor:color,data:navList});
        datasetsRate.push({label:f.label,borderColor:color,data:rate});
        datasetsDiff.push({label:f.label,borderColor:color,data:diff});
    });
    chartLine(document.getElementById("navChart"),labels,datasetsNAV);
    chartLine(document.getElementById("rateChart"),labels,datasetsRate);
    chartLine(document.getElementById("diffChart"),labels,datasetsDiff);
}
main();
