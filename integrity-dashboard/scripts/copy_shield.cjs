const fs = require('fs');

const srcPath = '/home/xibalba/Projects/INTEGRITY/xibalba-shield/src/app/page.tsx';
const destPath = '/home/xibalba/Projects/integrity-core/integrity-dashboard/src/pages/ShieldPage.tsx';

let content = fs.readFileSync(srcPath, 'utf8');

// Replace next/link with regular anchor tags
content = content.replace(/import Link from 'next\/link';\n/, '');
content = content.replace(/<Link /g, '<a ');
content = content.replace(/<\/Link>/g, '</a>');

// Replace component name
content = content.replace(/export default function Home\(\)/, 'export default function ShieldPage()');

fs.writeFileSync(destPath, content);
console.log('Successfully copied and transformed ShieldPage');
