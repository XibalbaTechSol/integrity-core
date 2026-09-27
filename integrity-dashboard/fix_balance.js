const fs = require('fs');

const content = fs.readFileSync('src/pages/ProtocolDashboardPage.tsx', 'utf8');
let openCount = 0;
let closeCount = 0;

for (let i = 0; i < content.length; i++) {
  if (content.substr(i, 4) === '<div') openCount++;
  if (content.substr(i, 5) === '</div') closeCount++;
}

console.log(`open <div>: ${openCount}`);
console.log(`close </div>: ${closeCount}`);
