const fs = require('fs');
let content = fs.readFileSync('src/pages/ShieldPage.tsx', 'utf8');
content = content.replace(/<Link href="/g, '<Link to="');
fs.writeFileSync('src/pages/ShieldPage.tsx', content);
