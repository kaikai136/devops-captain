import { createApp } from 'vue';
import ElementPlus from 'element-plus';
import zhCn from 'element-plus/es/locale/lang/zh-cn';
import 'element-plus/dist/index.css';

import SimpleHostTerminalPage from './components/terminal/SimpleHostTerminalPage.vue';
import './styles/simple-host-terminal.css';
import './styles/base/element-plus-theme.css';
import './styles/base/element-plus-overrides.css';
import '@xterm/xterm/css/xterm.css';

const app = createApp(SimpleHostTerminalPage);
app.use(ElementPlus, { locale: zhCn });
app.mount('#host-terminal-app');
