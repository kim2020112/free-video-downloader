<script setup>
import { computed, ref, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { Transformer } from 'markmap-lib'
import { Markmap } from 'markmap-view'

marked.setOptions({ gfm: true, breaks: true })

function renderMarkdown(text) {
  if (!text) return ''
  return DOMPurify.sanitize(marked.parse(text))
}

const props = defineProps({
  result: Object,
  loading: Boolean,
  error: String,
  streamingText: String,
  subtitleText: String,
  isFetchingSubtitle: Boolean,
  subtitleError: String,
  chatMessages: Array,
  isChatStreaming: Boolean,
  chatError: String,
  subtitleInfo: Object,
  videoTitle: String,
  mindmapMarkdown: String,
  onSummarize: Function,
  onFetchSubtitle: Function,
  onSendQuestion: Function,
})

const isLimitError = computed(() => props.error && props.error.includes('免费次数'))

const activeSubTab = ref('summary')
const chatInput = ref('')

const hasMindmap = computed(() => !!props.mindmapMarkdown)

function handleStart() {
  props.onSummarize()
}

function handleTabSubtitle() {
  activeSubTab.value = 'subtitle'
  if (!props.subtitleText && !props.isFetchingSubtitle && props.onFetchSubtitle) {
    props.onFetchSubtitle()
  }
}

function handleTabQA() {
  activeSubTab.value = 'qa'
  if (!props.subtitleText && !props.isFetchingSubtitle && props.onFetchSubtitle) {
    props.onFetchSubtitle()
  }
}

function sendChat() {
  if (!chatInput.value.trim() || props.isChatStreaming) return
  props.onSendQuestion(chatInput.value)
  chatInput.value = ''
}

// ──── 思维导图 (markmap) ────
const mindmapSvg = ref(null)
const mindmapContainer = ref(null)
const isFullscreen = ref(false)
let markmapInstance = null

watch(() => props.mindmapMarkdown, async (val) => {
  if (val) {
    await nextTick()
    renderMindmap(val)
  }
})

function renderMindmap(md) {
  if (!mindmapSvg.value) return
  try {
    mindmapSvg.value.innerHTML = ''
    const transformer = new Transformer()
    const { root } = transformer.transform(md)
    markmapInstance = Markmap.create(mindmapSvg.value, { autoFit: true, duration: 0 }, root)
    // 注入深色主题样式到 SVG 内部
    const styleEl = document.createElementNS('http://www.w3.org/2000/svg', 'style')
    styleEl.textContent = `
      .markmap-foreign { display: inline-block !important; }
      foreignObject { overflow: visible !important; }
      foreignObject div {
        font-size: 16px !important;
        font-family: 'Noto Sans SC', -apple-system, sans-serif !important;
        color: #E2E8F0 !important;
        background: rgba(15, 23, 42, 0.85) !important;
        padding: 4px 8px !important;
        border-radius: 4px !important;
        line-height: 1.6 !important;
      }
      .markmap-link { stroke: rgba(99, 102, 241, 0.35) !important; }
      .markmap-node-circle { fill: #6366F1 !important; stroke: #818CF8 !important; }
    `
    mindmapSvg.value.insertBefore(styleEl, mindmapSvg.value.firstChild)
  } catch (e) {
    console.warn('思维导图渲染失败:', e)
  }
}

function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
  nextTick(() => {
    if (markmapInstance) markmapInstance.fit()
  })
}

onMounted(() => document.addEventListener('fullscreenchange', onFullscreenChange))
onUnmounted(() => document.removeEventListener('fullscreenchange', onFullscreenChange))

function toggleFullscreen() {
  if (!mindmapContainer.value) return
  if (!document.fullscreenElement) {
    mindmapContainer.value.requestFullscreen()
  } else {
    document.exitFullscreen()
  }
}

function getSafeFilename() {
  return (props.videoTitle || 'mindmap').replace(/[\\/*?:"<>|]/g, '_').substring(0, 80)
}

function buildExportableSvg() {
  if (!mindmapSvg.value) return null
  const cloned = mindmapSvg.value.cloneNode(true)
  cloned.querySelectorAll('[transform]').forEach(el => {
    const t = el.getAttribute('transform')
    if (t && t.includes('NaN')) el.setAttribute('transform', 'translate(0,0) scale(1)')
  })
  cloned.querySelectorAll('foreignObject').forEach(fo => {
    const textContent = fo.textContent?.trim() || ''
    if (!textContent) { fo.remove(); return }
    const x = parseFloat(fo.getAttribute('x')) || 0
    const y = parseFloat(fo.getAttribute('y')) || 0
    const h = parseFloat(fo.getAttribute('height')) || 20
    const textEl = document.createElementNS('http://www.w3.org/2000/svg', 'text')
    textEl.setAttribute('x', String(x + 6))
    textEl.setAttribute('y', String(y + h / 2 + 1))
    textEl.setAttribute('font-size', '16')
    textEl.setAttribute('font-family', 'Noto Sans SC, -apple-system, sans-serif')
    textEl.setAttribute('fill', '#E2E8F0')
    textEl.setAttribute('font-weight', '500')
    textEl.setAttribute('dominant-baseline', 'middle')
    textEl.textContent = textContent
    fo.parentNode.replaceChild(textEl, fo)
  })
  return cloned
}

function serializeSvg(svgEl) {
  const serializer = new XMLSerializer()
  let svgString = serializer.serializeToString(svgEl)
  if (!svgString.includes('xmlns=')) {
    svgString = svgString.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"')
  }
  const styles = document.querySelectorAll('style')
  let markmapCss = ''
  styles.forEach(s => {
    if (s.textContent.includes('.markmap')) markmapCss += s.textContent
  })
  if (markmapCss) {
    svgString = svgString.replace('>', `><defs><style>${markmapCss}</style></defs>`)
  }
  return svgString
}

function getContentBBox() {
  const svgEl = mindmapSvg.value
  const gRoot = svgEl.querySelector('g')
  if (gRoot) {
    try {
      const bbox = gRoot.getBBox()
      if (bbox.width > 0 && bbox.height > 0) {
        const transform = gRoot.getAttribute('transform') || ''
        const translateMatch = transform.match(/translate\(\s*([-\d.e]+)\s*[,\s]\s*([-\d.e]+)\s*\)/)
        const scaleMatch = transform.match(/scale\(\s*([-\d.e]+)/)
        const tx = translateMatch ? parseFloat(translateMatch[1]) : 0
        const ty = translateMatch ? parseFloat(translateMatch[2]) : 0
        const sc = scaleMatch ? parseFloat(scaleMatch[1]) : 1
        return {
          x: bbox.x * sc + tx,
          y: bbox.y * sc + ty,
          width: bbox.width * sc,
          height: bbox.height * sc,
        }
      }
    } catch {}
  }
  try {
    const bbox = svgEl.getBBox()
    if (bbox.width > 0 && bbox.height > 0) return bbox
  } catch {}
  return { x: 0, y: 0, width: 800, height: 600 }
}

function setFullViewBox(svgClone) {
  const dims = getContentBBox()
  const padding = 60
  const vx = dims.x - padding; const vy = dims.y - padding
  const vw = dims.width + padding * 2; const vh = dims.height + padding * 2
  svgClone.setAttribute('viewBox', `${vx} ${vy} ${vw} ${vh}`)
  svgClone.setAttribute('width', String(vw))
  svgClone.setAttribute('height', String(vh))
  return { vw, vh }
}

function downloadSVG() {
  if (!mindmapSvg.value) return
  const exportSvg = buildExportableSvg()
  if (!exportSvg) return
  setFullViewBox(exportSvg)
  const svgString = serializeSvg(exportSvg)
  const blob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
  triggerDownload(blob, `${getSafeFilename()} - 思维导图.svg`)
}

function downloadPNG() {
  if (!mindmapSvg.value) return
  const exportSvg = buildExportableSvg()
  if (!exportSvg) return
  const { vw, vh } = setFullViewBox(exportSvg)
  const scale = Math.max(4, Math.ceil(3840 / vw))
  const svgString = serializeSvg(exportSvg)
  const canvas = document.createElement('canvas')
  canvas.width = vw * scale; canvas.height = vh * scale
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#0F172A'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  const img = new Image()
  const blob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  img.onload = () => {
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    URL.revokeObjectURL(url)
    canvas.toBlob((pngBlob) => {
      if (pngBlob) triggerDownload(pngBlob, `${getSafeFilename()} - 思维导图.png`)
    }, 'image/png')
  }
  img.onerror = () => URL.revokeObjectURL(url)
  img.src = url
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename
  document.body.appendChild(a); a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// ──── 字幕格式转换 ────
function pad2(n) { return String(n).padStart(2, '0') }
function pad3(n) { return String(Math.round(n)).padStart(3, '0') }

function formatTimeSRT(ms) {
  const h = Math.floor(ms / 3600000)
  const m = Math.floor((ms % 3600000) / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  const millis = ms % 1000
  return `${pad2(h)}:${pad2(m)}:${pad2(s)},${pad3(millis)}`
}

function formatTimeVTT(ms) {
  const h = Math.floor(ms / 3600000)
  const m = Math.floor((ms % 3600000) / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  const millis = ms % 1000
  return `${pad2(h)}:${pad2(m)}:${pad2(s)}.${pad3(millis)}`
}

function segmentsToSRT(segments) {
  return segments.map((seg, i) => {
    const start = formatTimeSRT((seg.start || 0) * 1000)
    const end = formatTimeSRT((seg.end || 0) * 1000)
    return `${i + 1}\n${start} --> ${end}\n${seg.text}`
  }).join('\n\n')
}

function segmentsToVTT(segments) {
  const lines = ['WEBVTT', '']
  for (const seg of segments) {
    const start = formatTimeVTT((seg.start || 0) * 1000)
    const end = formatTimeVTT((seg.end || 0) * 1000)
    lines.push(`${start} --> ${end}`)
    lines.push(seg.text)
    lines.push('')
  }
  return lines.join('\n')
}

function segmentsToTXT(segments) {
  return segments.map(s => s.text).join('\n\n')
}

const subtitleFormat = ref('srt')

function downloadSubtitle() {
  const segments = props.subtitleInfo?.segments
  if (!segments || !segments.length) return
  let content, ext, mime
  const fmt = subtitleFormat.value
  if (fmt === 'vtt') {
    content = segmentsToVTT(segments); ext = 'vtt'; mime = 'text/vtt'
  } else if (fmt === 'txt') {
    content = segmentsToTXT(segments); ext = 'txt'; mime = 'text/plain'
  } else {
    content = segmentsToSRT(segments); ext = 'srt'; mime = 'text/plain'
  }
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${props.videoTitle || 'subtitle'}.${ext}`
  a.click()
  URL.revokeObjectURL(url)
}

const hasSubtitleSegments = computed(() =>
  props.subtitleInfo?.segments && props.subtitleInfo.segments.length > 0
)
</script>

<template>
  <div class="ai-summary">
    <!-- 未开始状态 -->
    <div v-if="!result && !loading && !error" class="summary-trigger">
      <button @click="handleStart" class="summarize-btn">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="summarize-icon">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
        </svg>
        AI 一键总结
      </button>
      <p class="summary-hint">基于视频字幕，AI 自动生成摘要和思维导图</p>
    </div>

    <!-- 错误状态 -->
    <div v-if="error && !loading" class="summary-error" :class="{ 'summary-error-limit': isLimitError }">
      <template v-if="isLimitError">
        <div class="limit-content">
          <div class="limit-header">
            <svg class="limit-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" /></svg>
            <span class="limit-title">今日免费次数已用完</span>
          </div>
          <p class="limit-desc">每日 3 次免费 AI 总结已用尽，升级 Pro 解锁无限次使用</p>
          <button class="pro-btn">升级 Pro</button>
        </div>
      </template>
      <template v-else>
        <svg class="error-icon" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" /></svg>
        <span>{{ error }}</span>
        <button @click="onSummarize" class="retry-btn">重试</button>
      </template>
    </div>

    <!-- 结果展示区（含 4 个子 Tab） -->
    <div v-if="result || loading" class="summary-content">
      <!-- 子 Tab 栏 -->
      <div class="sub-tab-bar">
        <button class="sub-tab-btn" :class="{ active: activeSubTab === 'summary' }" @click="activeSubTab = 'summary'">
          摘要
        </button>
        <button class="sub-tab-btn" :class="{ active: activeSubTab === 'subtitle' }" @click="handleTabSubtitle">
          字幕
        </button>
        <button
          class="sub-tab-btn"
          :class="{ active: activeSubTab === 'mindmap' }"
          :disabled="!hasMindmap"
          @click="activeSubTab = 'mindmap'"
        >
          思维导图
        </button>
        <button class="sub-tab-btn" :class="{ active: activeSubTab === 'qa' }" @click="handleTabQA">
          问答
        </button>
      </div>

      <!-- Tab: 摘要 -->
      <div v-show="activeSubTab === 'summary'" class="sub-tab-panel">
        <div v-if="loading && !streamingText" class="loading-skeleton">
          <div class="skeleton-line skeleton-title"></div>
          <div class="skeleton-line skeleton-long"></div>
          <div class="skeleton-line skeleton-medium"></div>
          <div class="skeleton-line skeleton-long"></div>
          <div class="skeleton-line skeleton-short"></div>
        </div>
        <div v-else class="summary-section">
          <div class="summary-text prose prose-invert prose-sm max-w-none" v-html="renderMarkdown(streamingText || result.summary)"></div>
        </div>
        <p v-if="loading && streamingText" class="streaming-indicator">AI 正在生成中...</p>
        <button v-if="!loading" @click="onSummarize" class="regenerate-btn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="regenerate-icon"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" /></svg>
          重新生成
        </button>
      </div>

      <!-- Tab: 字幕 -->
      <div v-show="activeSubTab === 'subtitle'" class="sub-tab-panel">
        <div v-if="isFetchingSubtitle" class="subtitle-loading">
          <div class="skeleton-line skeleton-long"></div>
          <div class="skeleton-line skeleton-long"></div>
          <div class="skeleton-line skeleton-medium"></div>
        </div>
        <div v-else-if="subtitleError" class="subtitle-error-msg">{{ subtitleError }}</div>
        <div v-else-if="subtitleText">
          <div class="subtitle-toolbar">
            <div class="subtitle-format-select">
              <select v-model="subtitleFormat" class="format-select">
                <option value="srt">SRT</option>
                <option value="vtt">VTT</option>
                <option value="txt">TXT</option>
              </select>
            </div>
            <button
              class="subtitle-download-btn"
              :disabled="!hasSubtitleSegments"
              :title="!hasSubtitleSegments ? '该字幕无分段数据，仅支持在线查看' : '下载字幕文件'"
              @click="downloadSubtitle"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" class="download-icon"><path d="M10.75 2.75a.75.75 0 00-1.5 0v8.614L6.295 8.235a.75.75 0 10-1.09 1.03l4.25 4.5a.75.75 0 001.09 0l4.25-4.5a.75.75 0 00-1.09-1.03l-2.955 3.129V2.75z"/><path d="M3.5 12.75a.75.75 0 00-1.5 0v2.5A2.75 2.75 0 004.75 18h10.5A2.75 2.75 0 0018 15.25v-2.5a.75.75 0 00-1.5 0v2.5c0 .69-.56 1.25-1.25 1.25H4.75c-.69 0-1.25-.56-1.25-1.25v-2.5z"/></svg>
              下载
            </button>
          </div>
          <div class="subtitle-text-wrapper">
            <pre class="subtitle-text">{{ subtitleText }}</pre>
          </div>
        </div>
        <div v-else class="subtitle-empty">
          <p class="subtitle-empty-text">该视频无可用的字幕文本</p>
          <p class="subtitle-empty-hint">部分视频仅含弹幕（非转录文本），无法用于 AI 总结或展示</p>
        </div>
      </div>

      <!-- Tab: 思维导图 -->
      <div v-show="activeSubTab === 'mindmap'" class="sub-tab-panel">
        <div v-if="hasMindmap">
          <div class="mindmap-controls">
            <button @click="downloadSVG" class="zoom-btn" title="下载 SVG">
              <svg viewBox="0 0 20 20" fill="currentColor" class="toolbar-icon"><path fill-rule="evenodd" d="M6 2a2 2 0 00-2 2v12a2 2 0 002 2h8a2 2 0 002-2V7.414A2 2 0 0015.414 6L13 3.586A2 2 0 0011.586 3H6zm5 13a1 1 0 102 0V8.414l2.293 2.293a1 1 0 001.414-1.414l-4-4a1 1 0 00-1.414 0l-4 4a1 1 0 001.414 1.414L11 8.414V15z" clip-rule="evenodd"/></svg>
              SVG
            </button>
            <button @click="downloadPNG" class="zoom-btn" title="下载 PNG">
              <svg viewBox="0 0 20 20" fill="currentColor" class="toolbar-icon"><path fill-rule="evenodd" d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z" clip-rule="evenodd"/></svg>
              PNG
            </button>
            <button @click="toggleFullscreen" class="zoom-btn" :title="isFullscreen ? '退出全屏' : '全屏展示'">
              <svg v-if="!isFullscreen" viewBox="0 0 20 20" fill="currentColor" class="toolbar-icon"><path d="M3 4a1 1 0 011-1h4a1 1 0 010 2H6.414l3.293 3.293a1 1 0 01-1.414 1.414L5 6.414V8a1 1 0 01-2 0V4zm9 1a1 1 0 010-2h4a1 1 0 011 1v4a1 1 0 01-2 0V6.414l-3.293 3.293a1 1 0 11-1.414-1.414L13.586 5H12zm-9 7a1 1 0 012 0v1.586l3.293-3.293a1 1 0 011.414 1.414L6.414 15H8a1 1 0 010 2H4a1 1 0 01-1-1v-4zm13-1a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 010-2h1.586l-3.293-3.293a1 1 0 011.414-1.414L15 13.586V12a1 1 0 011-1z"/></svg>
              <svg v-else viewBox="0 0 20 20" fill="currentColor" class="toolbar-icon"><path d="M6 18L18 6M6 6l12 12" stroke="currentColor" stroke-width="2"/></svg>
              {{ isFullscreen ? '退出' : '全屏' }}
            </button>
          </div>
          <div ref="mindmapContainer" class="mindmap-container" :class="{ 'mindmap-fullscreen': isFullscreen }">
            <svg ref="mindmapSvg" class="mindmap-svg" :style="isFullscreen ? 'height: 100%' : 'min-height: 500px'"></svg>
          </div>
        </div>
        <div v-else-if="loading" class="mindmap-loading">
          <div class="skeleton-line skeleton-long"></div>
          <div class="skeleton-line skeleton-medium"></div>
          <p class="loading-text">正在生成思维导图...</p>
        </div>
        <div v-else class="mindmap-empty">请先生成总结以查看思维导图</div>
      </div>

      <!-- Tab: 问答 -->
      <div v-show="activeSubTab === 'qa'" class="sub-tab-panel">
        <div class="chat-container">
          <div v-if="!subtitleText && !isFetchingSubtitle" class="chat-need-subtitle">
            <p>请先加载字幕文本以使用问答功能</p>
            <button @click="onFetchSubtitle" class="fetch-subtitle-btn">加载字幕</button>
          </div>
          <template v-else>
            <div class="chat-messages" ref="chatMessagesEl">
              <div v-if="chatMessages.length === 0" class="chat-empty">
                基于视频字幕内容的 AI 问答，请输入你的问题
              </div>
              <div v-for="(msg, i) in chatMessages" :key="i" class="chat-message" :class="'chat-msg-' + msg.role">
                <span class="chat-role">{{ msg.role === 'user' ? '你' : 'AI' }}</span>
                <div class="chat-content prose prose-invert prose-sm max-w-none" v-html="renderMarkdown(msg.content)"></div>
              </div>
              <div v-if="chatError" class="chat-error">{{ chatError }}</div>
            </div>
            <div class="chat-input-row">
              <textarea
                v-model="chatInput"
                class="chat-input"
                placeholder="基于视频字幕提问..."
                rows="2"
                :disabled="isChatStreaming"
                @keydown.enter.exact.prevent="sendChat"
              ></textarea>
              <button @click="sendChat" :disabled="isChatStreaming || !chatInput.trim()" class="chat-send-btn">
                <svg v-if="!isChatStreaming" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="send-icon"><path stroke-linecap="round" stroke-linejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" /></svg>
                <svg v-else class="send-icon spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" /></svg>
              </button>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ai-summary { padding: 0; }

/* 触发按钮 */
.summary-trigger { display: flex; flex-direction: column; align-items: center; gap: 0.75rem; padding: 2rem 1rem; }
.summarize-btn { display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.75rem 1.5rem; background: linear-gradient(135deg, rgba(139, 92, 246, 0.2) 0%, rgba(59, 130, 246, 0.2) 100%); border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 10px; color: #C4B5FD; font-size: 0.9375rem; font-weight: 600; cursor: pointer; transition: all 0.2s; }
.summarize-btn:hover { background: linear-gradient(135deg, rgba(139, 92, 246, 0.3) 0%, rgba(59, 130, 246, 0.3) 100%); border-color: rgba(139, 92, 246, 0.5); transform: translateY(-1px); }
.summarize-icon { width: 20px; height: 20px; }
.summary-hint { font-size: 0.8125rem; color: var(--text-muted); text-align: center; }

/* 加载 */
.summary-loading { padding: 1.5rem; display: flex; flex-direction: column; gap: 0.75rem; }
.loading-skeleton { display: flex; flex-direction: column; gap: 0.75rem; }
.skeleton-line { height: 16px; background: linear-gradient(90deg, rgba(255,255,255,0.05) 25%, rgba(255,255,255,0.1) 50%, rgba(255,255,255,0.05) 75%); background-size: 200% 100%; animation: skeleton-shimmer 1.5s infinite; border-radius: 4px; }
.skeleton-title { width: 40%; height: 20px; }
.skeleton-long { width: 100%; }
.skeleton-medium { width: 75%; }
.skeleton-short { width: 50%; }
@keyframes skeleton-shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
.loading-text { font-size: 0.8125rem; color: var(--text-muted); text-align: center; margin-top: 0.5rem; }

.streaming-indicator { display: inline-flex; align-items: center; gap: 0.375rem; font-size: 0.8125rem; color: var(--text-muted); margin-top: 0.5rem; }
.streaming-indicator::before { content: ''; width: 6px; height: 6px; background: var(--accent-blue); border-radius: 50%; animation: pulse-dot 1s infinite; }
@keyframes pulse-dot { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

/* 流式文本 */
.streaming-text { min-height: 60px; padding: 0.75rem 1rem; border: 1px solid var(--border); border-radius: 8px; background: rgba(255,255,255,0.02); }
.streaming-text :deep(pre) { background: rgba(0,0,0,0.3); padding: 0.75rem 1rem; border-radius: 6px; overflow-x: auto; }
.streaming-text :deep(blockquote) { border-left-color: var(--accent-blue); }
.streaming-text :deep(a) { color: var(--accent-blue); }

/* 子 Tab 栏 */
.sub-tab-bar { display: flex; gap: 0; border-bottom: 1px solid var(--border); margin-bottom: 1.25rem; }
.sub-tab-btn { padding: 0.625rem 1rem; background: transparent; border: none; border-bottom: 2px solid transparent; color: var(--text-muted); font-size: 0.875rem; font-weight: 500; cursor: pointer; transition: all 0.15s; }
.sub-tab-btn:hover { color: var(--text-secondary); }
.sub-tab-btn.active { color: var(--accent-blue); border-bottom-color: var(--accent-blue); }
.sub-tab-btn:disabled { color: var(--border); cursor: not-allowed; }

.sub-tab-panel { min-height: 100px; }

/* 摘要 */
.summary-section { padding: 0; margin-bottom: 1.25rem; }
.summary-text { margin: 0; }
.summary-text :deep(pre) { background: rgba(0,0,0,0.3); padding: 0.75rem 1rem; border-radius: 6px; overflow-x: auto; }
.summary-text :deep(blockquote) { border-left-color: var(--accent-blue); }
.summary-text :deep(a) { color: var(--accent-blue); }

/* 字幕展示 */
.subtitle-toolbar { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; }
.format-select { padding: 0.375rem 0.5rem; background: rgba(255,255,255,0.05); border: 1px solid var(--border); border-radius: 6px; color: var(--text-secondary); font-size: 0.8125rem; outline: none; cursor: pointer; }
.format-select:focus { border-color: var(--accent-blue); }
.subtitle-download-btn { display: inline-flex; align-items: center; gap: 0.375rem; padding: 0.375rem 0.75rem; background: rgba(59, 130, 246, 0.12); border: 1px solid rgba(59, 130, 246, 0.25); border-radius: 6px; color: #93C5FD; font-size: 0.8125rem; font-weight: 500; cursor: pointer; transition: all 0.15s; }
.subtitle-download-btn:hover:not(:disabled) { background: rgba(59, 130, 246, 0.2); border-color: rgba(59, 130, 246, 0.4); }
.subtitle-download-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.download-icon { width: 14px; height: 14px; }
.subtitle-text-wrapper {
  max-height: 500px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.75rem;
  background: rgba(0, 0, 0, 0.15);
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,0.12) transparent;
}
.subtitle-text-wrapper::-webkit-scrollbar { width: 6px; }
.subtitle-text-wrapper::-webkit-scrollbar-track { background: transparent; }
.subtitle-text-wrapper::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.12); border-radius: 3px; }
.subtitle-text-wrapper::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }
.subtitle-text { font-family: 'Noto Sans SC', monospace; font-size: 0.8125rem; line-height: 1.6; color: var(--text-secondary); white-space: pre-wrap; margin: 0; }
.subtitle-empty { padding: 2rem; text-align: center; }
.subtitle-empty-text { font-size: 0.9375rem; color: var(--text-secondary); margin: 0 0 0.5rem 0; }
.subtitle-empty-hint { font-size: 0.8125rem; color: var(--text-muted); margin: 0; }
.subtitle-loading { display: flex; flex-direction: column; gap: 0.5rem; padding: 1rem; }
.subtitle-error-msg { color: #FCA5A5; padding: 1rem; font-size: 0.875rem; }
.fetch-subtitle-btn { padding: 0.5rem 1.25rem; background: rgba(59, 130, 246, 0.15); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 8px; color: #93C5FD; font-size: 0.875rem; cursor: pointer; }

/* 思维导图 */
.mindmap-controls { display: flex; align-items: center; justify-content: flex-end; gap: 0.375rem; margin-bottom: 0.75rem; flex-wrap: wrap; }
.zoom-btn {
  display: inline-flex; align-items: center; gap: 0.25rem;
  height: 30px; padding: 0 0.625rem;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 7px;
  color: var(--text-secondary);
  font-size: 0.75rem; font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}
.zoom-btn:hover { background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.18); color: var(--text-primary); }
.toolbar-icon { width: 14px; height: 14px; }
.mindmap-container {
  overflow: hidden;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 10px;
  background: #0F172A;
}
.mindmap-svg { display: block; width: 100%; min-height: 500px; }
.mindmap-empty { padding: 2rem; text-align: center; color: var(--text-muted); }
.mindmap-loading { display: flex; flex-direction: column; align-items: center; gap: 0.75rem; padding: 2rem; }
.mindmap-loading .loading-text { font-size: 0.8125rem; color: var(--text-muted); margin: 0; }

/* markmap 自定义样式 */
.mindmap-container :deep(.markmap-foreign) { display: inline-block !important; }
.mindmap-container :deep(foreignObject) { overflow: visible !important; }
.mindmap-container :deep(foreignObject div) {
  font-size: 16px !important;
  font-family: 'Noto Sans SC', -apple-system, sans-serif !important;
  color: #E2E8F0 !important;
  background: rgba(15, 23, 42, 0.85) !important;
  padding: 4px 8px !important;
  border-radius: 4px !important;
  line-height: 1.6 !important;
}

/* 全屏 */
.mindmap-fullscreen {
  position: fixed !important; top: 0; left: 0; right: 0; bottom: 0;
  z-index: 50; border-radius: 0 !important; border: none !important;
  background: #0F172A;
}
.mindmap-container:fullscreen { background: #0F172A; display: flex; align-items: center; justify-content: center; }
.mindmap-container:fullscreen .mindmap-svg { max-width: 100vw; max-height: 100vh; }

/* 问答 */
.chat-container { display: flex; flex-direction: column; height: 400px; }
.chat-need-subtitle { padding: 2rem; text-align: center; color: var(--text-muted); }
.chat-messages { flex: 1; overflow-y: auto; padding: 0.5rem 0; display: flex; flex-direction: column; gap: 0.75rem; }
.chat-empty { text-align: center; color: var(--text-muted); font-size: 0.8125rem; padding: 2rem 1rem; }
.chat-message { padding: 0.625rem 0.875rem; border-radius: 8px; max-width: 90%; }
.chat-msg-user { align-self: flex-end; background: rgba(59, 130, 246, 0.15); border: 1px solid rgba(59, 130, 246, 0.2); }
.chat-msg-assistant { align-self: flex-start; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--border); }
.chat-role { font-size: 0.6875rem; font-weight: 600; color: var(--text-muted); margin-bottom: 0.25rem; display: block; }
.chat-content { margin: 0; }
.chat-content :deep(pre) { background: rgba(0,0,0,0.3); padding: 0.5rem 0.75rem; border-radius: 4px; overflow-x: auto; font-size: 0.8125rem; }
.chat-content :deep(blockquote) { border-left-color: var(--accent-blue); }
.chat-content :deep(a) { color: var(--accent-blue); }
.chat-error { color: #FCA5A5; font-size: 0.75rem; padding: 0.25rem 0.5rem; }
.chat-input-row { display: flex; gap: 0.5rem; margin-top: 0.5rem; padding-top: 0.75rem; border-top: 1px solid var(--border); }
.chat-input { flex: 1; padding: 0.625rem 0.75rem; background: rgba(255,255,255,0.05); border: 1px solid var(--border); border-radius: 8px; color: var(--text-primary); font-size: 0.875rem; resize: none; outline: none; font-family: inherit; }
.chat-input:focus { border-color: var(--accent-blue); }
.chat-send-btn { padding: 0.5rem 0.875rem; background: linear-gradient(135deg, var(--accent-blue) 0%, var(--accent-cyan) 100%); border: none; border-radius: 8px; color: white; cursor: pointer; display: flex; align-items: center; }
.chat-send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.send-icon { width: 18px; height: 18px; }
.spinner { animation: spin 1.5s linear infinite; }
@keyframes spin { 100% { transform: rotate(360deg); } }

/* 错误 */
.summary-error { display: flex; align-items: center; gap: 0.75rem; padding: 1rem 1.25rem; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: var(--radius); color: #FCA5A5; font-size: 0.875rem; }
.summary-error .error-icon { width: 18px; height: 18px; flex-shrink: 0; }
.retry-btn { margin-left: auto; padding: 0.25rem 0.75rem; background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 6px; color: #FCA5A5; font-size: 0.8125rem; cursor: pointer; }
.summary-error-limit { background: linear-gradient(135deg, rgba(139, 92, 246, 0.1) 0%, rgba(59, 130, 246, 0.1) 100%); border-color: rgba(139, 92, 246, 0.25); padding: 1.25rem; }
.limit-content { display: flex; flex-direction: column; gap: 0.75rem; width: 100%; }
.limit-header { display: flex; align-items: center; gap: 0.5rem; }
.limit-icon { width: 20px; height: 20px; color: #FCD34D; }
.limit-title { font-size: 0.9375rem; font-weight: 600; color: var(--text-primary); }
.limit-desc { font-size: 0.8125rem; color: var(--text-muted); margin: 0; }
.pro-btn { display: inline-flex; align-items: center; justify-content: center; gap: 0.375rem; padding: 0.5rem 1.25rem; background: linear-gradient(135deg, #8B5CF6 0%, #3B82F6 100%); border: none; border-radius: 8px; color: white; font-size: 0.875rem; font-weight: 600; cursor: pointer; align-self: flex-start; }
.pro-btn:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(139, 92, 246, 0.3); }

.regenerate-btn { display: inline-flex; align-items: center; gap: 0.375rem; padding: 0.5rem 1rem; background: transparent; border: 1px solid var(--border); border-radius: 8px; color: var(--text-muted); font-size: 0.8125rem; cursor: pointer; margin-top: 0.5rem; }
.regenerate-btn:hover { background: var(--bg-card-hover); border-color: var(--border-hover); color: var(--text-primary); }
.regenerate-icon { width: 16px; height: 16px; }

@media (max-width: 768px) {
  .mindmap-container { padding: 0.5rem; }
  .chat-container { height: 300px; }
}
</style>
