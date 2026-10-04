import { AxiosError } from 'axios';
import { useCommentary } from '../../hooks/useStockAnalysis';
import type { CommentaryResponse } from '../../api/types';

interface Props {
  tsCode: string;
}

/**
 * 提取一段文本中的"金句"——优先匹配双引号/「」内容，
 * 否则取首句或最强语气句（包含"你给我记住"/"记住"/"必须"等关键词）。
 */
function extractKeyQuote(text: string): string {
  const quoted = text.match(/[「"']([^」"']{6,40})[」"']/);
  if (quoted) return quoted[1];

  const strongKeywords = ['你给我记住', '记住', '必须', '一定要', '永远不', '少妇战法'];
  for (const kw of strongKeywords) {
    const idx = text.indexOf(kw);
    if (idx >= 0) {
      const slice = text.slice(idx, idx + 60);
      const endPunc = slice.search(/[。!?\n]/);
      return endPunc > 0 ? slice.slice(0, endPunc) : slice;
    }
  }

  const firstSentence = text.split(/[。!?]/)[0];
  if (firstSentence && firstSentence.length <= 60) return firstSentence;

  return '';
}

/**
 * 把文本按"1./2./3./4."编号切分成段落。
 */
interface Section { title: string; body: string }

function splitIntoSections(text: string): Section[] {
  const numberMatches = [...text.matchAll(/(\d+)\.\s*([^\n.]{2,16})[。:：\n]/g)];

  if (numberMatches.length >= 2) {
    const sections: Section[] = [];
    for (let i = 0; i < numberMatches.length; i++) {
      const start = numberMatches[i].index! + numberMatches[i][0].length;
      const end = i + 1 < numberMatches.length ? numberMatches[i + 1].index! : text.length;
      sections.push({
        title: `${numberMatches[i][1]}. ${numberMatches[i][2].trim()}`,
        body: text.slice(start, end).trim(),
      });
    }
    return sections;
  }

  return [{ title: '', body: text.trim() }];
}

/**
 * 把数字识别为不同类型，渲染成对应的 inline badge：
 *   - 价格 (2-3 位整数 + .XX)         → 金色 "¥95.39"
 *   - MACD 等小数指标 (整数.X+)        → 紫色 "9.1518"
 *   - 百分比 (任意数字 + %)            → 蓝色 "+5.27%"
 *
 * 这样 95.39、72.48 这种关键价位立刻"跳出来"，用户一眼能识别。
 *
 * 同时支持 **加粗**（金色加粗）
 */
function renderInline(text: string): string {
  // 1. 先抽出 **加粗**，用占位符保护避免被数字替换打散
  const boldSegments: string[] = [];
  let protectedText = text.replace(/\*\*(.+?)\*\*/g, (_m, p1) => {
    const idx = boldSegments.length;
    boldSegments.push(`<strong class="text-accent-gold font-bold">${p1}</strong>`);
    return `\u0001BOLD${idx}\u0001`;
  });

  // 2. 把换行转成 <br/>
  protectedText = protectedText.replace(/\n/g, '<br/>');

  // 3. 百分比：xx.xx% / xx%  → 蓝色 badge
  protectedText = protectedText.replace(
    /([+-]?\d+(?:\.\d+)?)%/g,
    '<span class="inline-flex items-center px-1.5 py-0.5 mx-0.5 rounded font-mono tabular-nums text-[11px] font-bold bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/30">$1%</span>'
  );

  // 4. 价格：2-3 位整数 + 小数点 + 2 位小数（如 95.39 / 72.48 / 102.40）→ 金色 ¥ badge
  protectedText = protectedText.replace(
    /(^|[^\d.%])(\d{2,3}\.\d{2})(?!\d)/g,
    '$1<span class="inline-flex items-center px-1.5 py-0.5 mx-0.5 rounded font-mono tabular-nums text-[11px] font-bold bg-accent-gold/15 text-accent-gold border border-accent-gold/30">¥$2</span>'
  );

  // 5. 指标小数：整数.3+位小数（如 9.1518）→ 紫色 badge
  protectedText = protectedText.replace(
    /(^|[^\d.%])(\d+\.\d{3,})(?!\d)/g,
    '$1<span class="inline-flex items-center px-1.5 py-0.5 mx-0.5 rounded font-mono tabular-nums text-[11px] font-bold bg-accent-purple/15 text-accent-purple border border-accent-purple/30">$2</span>'
  );

  // 6. 还原 **加粗**
  // eslint-disable-next-line no-control-regex -- 使用 \u0001 作为临时占位符，避免与后续正则冲突
  protectedText = protectedText.replace(/\u0001BOLD(\d+)\u0001/g, (_m, idx) => boldSegments[Number(idx)]);

  return protectedText;
}

function Skeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-16 bg-bg-hover/60 rounded-lg w-full"></div>
      <div className="space-y-2">
        <div className="h-3 bg-bg-hover/60 rounded w-1/3"></div>
        <div className="h-3 bg-bg-hover/60 rounded w-full"></div>
        <div className="h-3 bg-bg-hover/60 rounded w-11/12"></div>
      </div>
      <div className="space-y-2">
        <div className="h-3 bg-bg-hover/60 rounded w-1/4"></div>
        <div className="h-3 bg-bg-hover/60 rounded w-full"></div>
      </div>
      <div className="space-y-2">
        <div className="h-3 bg-bg-hover/60 rounded w-1/4"></div>
        <div className="h-3 bg-bg-hover/60 rounded w-10/12"></div>
      </div>
    </div>
  );
}

export default function CommentaryCard({ tsCode }: Props) {
  const { data, isLoading, isError, error, refetch } = useCommentary(tsCode);

  const axiosError = error instanceof AxiosError ? error : null;
  const isNotConfigured = axiosError?.response?.status === 503;
  const isFailed = axiosError?.response?.status === 502;

  return (
    <div className="relative overflow-hidden rounded-2xl border border-accent-gold/30 bg-gradient-to-br from-bg-card via-bg-secondary to-bg-card shadow-[0_0_40px_-15px_rgba(245,158,11,0.25)]">
      {/* 装饰：左上角巨型引号 */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-6 -left-2 text-[180px] leading-none font-black text-accent-gold/[0.06] select-none"
        style={{ fontFamily: 'Georgia, serif' }}
      >
        "
      </div>
      {/* 装饰：右上角光斑 */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-20 -right-20 w-72 h-72 rounded-full bg-accent-gold/10 blur-3xl"
      />

      {/* Header */}
      <div className="relative border-b border-accent-gold/20 px-7 py-4 flex items-center justify-between bg-gradient-to-r from-accent-gold/[0.08] via-transparent to-accent-gold/[0.04]">
        <div className="flex items-center gap-4">
          <div className="relative">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-accent-gold to-accent-orange flex items-center justify-center font-black text-bg-primary text-2xl shadow-lg shadow-accent-gold/30">
              Z
            </div>
            <div className="absolute -bottom-1 -right-1 w-3 h-3 rounded-full bg-accent-green border-2 border-bg-card animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-black text-text-primary tracking-wide">Z哥点评</h3>
              <span className="text-[10px] text-accent-gold bg-accent-gold/10 border border-accent-gold/30 px-2 py-0.5 rounded-full font-bold tracking-wider">
                AI · 金句
              </span>
            </div>
            <div className="text-[10px] text-text-muted mt-0.5 tracking-wider uppercase">
              Z哥量化 · 思维框架蒸馏
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {data?.cached && (
            <span className="text-[10px] text-text-muted bg-bg-hover/60 px-2 py-1 rounded-full border border-border/30">
              已缓存
            </span>
          )}
          {data && !isLoading && (
            <button
              onClick={() => refetch()}
              className="text-text-muted hover:text-accent-gold transition-all text-xs px-2.5 py-1 rounded-md hover:bg-accent-gold/10 border border-transparent hover:border-accent-gold/30 hover:shadow-sm"
              title="重新生成"
            >
              ↻ 刷新
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="relative p-7">
        {isLoading && <Skeleton />}

        {isNotConfigured && (
          <div className="text-sm text-text-muted text-center py-10">
            <div className="text-4xl mb-3 opacity-60">🔑</div>
            <div className="text-text-secondary mb-1">Z哥点评需要配置 LLM API Key</div>
            <div className="text-xs mt-2 text-text-muted/70">在 <code className="text-accent-gold">.env</code> 中设置 LLM_API_KEY</div>
          </div>
        )}

        {isFailed && !isNotConfigured && (
          <div className="text-sm text-accent-red text-center py-10">
            <div className="text-3xl mb-3 opacity-70">⚠️</div>
            <div>LLM 生成失败</div>
            <button
              onClick={() => refetch()}
              className="mt-4 text-xs text-accent-gold hover:underline"
            >
              重试
            </button>
          </div>
        )}

        {isError && !isNotConfigured && !isFailed && (
          <div className="text-sm text-accent-red text-center py-10">
            <div className="text-3xl mb-3 opacity-70">⚠️</div>
            <div>加载失败</div>
            <button
              onClick={() => refetch()}
              className="mt-4 text-xs text-accent-gold hover:underline"
            >
              重试
            </button>
          </div>
        )}

        {data && !isLoading && data.commentary_text && !data.error && (
          <CommentaryBody data={data} />
        )}
      </div>
    </div>
  );
}

/**
 * 评论主体：金句 callout + 分段正文 + meta
 */
function CommentaryBody({ data }: { data: CommentaryResponse }) {
  const keyQuote = extractKeyQuote(data.commentary_text);
  const sections = splitIntoSections(data.commentary_text);

  return (
    <div className="space-y-6">
      {/* 金句 callout */}
      {keyQuote && (
        <div className="relative rounded-xl border border-accent-gold/40 bg-gradient-to-br from-accent-gold/[0.12] via-accent-gold/[0.06] to-transparent px-6 py-5">
          <div className="absolute top-3 left-3 text-accent-gold/40 text-3xl font-serif leading-none">"</div>
          <div className="absolute bottom-3 right-3 text-accent-gold/40 text-3xl font-serif leading-none">"</div>
          <div className="text-center text-base md:text-lg font-bold text-accent-gold leading-relaxed px-6 tracking-wide"
               style={{ textShadow: '0 0 20px rgba(245,158,11,0.15)' }}>
            {keyQuote}
          </div>
          <div className="text-center mt-3">
            <span className="text-[10px] text-accent-gold/70 font-semibold tracking-[0.3em] uppercase">
              — Z哥金句 —
            </span>
          </div>
        </div>
      )}

      {/* 分段正文 */}
      <div className="space-y-5">
        {sections.map((section, idx) => (
          <div key={idx} className="space-y-2">
            {section.title && (
              <div className="flex items-center gap-3">
                <div className="flex-shrink-0 w-7 h-7 rounded-md bg-accent-gold/15 border border-accent-gold/30 flex items-center justify-center text-xs font-black text-accent-gold">
                  {section.title.match(/^\d+/)?.[0] || idx + 1}
                </div>
                <div className="text-sm font-bold text-text-primary tracking-wide">
                  {section.title.replace(/^\d+\.\s*/, '')}
                </div>
                <div className="flex-1 h-px bg-gradient-to-r from-accent-gold/30 via-accent-gold/10 to-transparent" />
              </div>
            )}
            <div
              className="text-sm text-text-secondary leading-[1.85] pl-10 whitespace-pre-wrap tracking-wide"
              dangerouslySetInnerHTML={{ __html: renderInline(section.body) }}
            />
          </div>
        ))}
      </div>

      {/* Meta 信息 */}
      <div className="pt-4 mt-2 border-t border-border/30 flex items-center justify-between text-[10px] text-text-muted/70">
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1">
            <span className="w-1 h-1 rounded-full bg-accent-gold/60"></span>
            {data.generated_at}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-text-muted/50">model</span>
          <span className="font-mono text-accent-gold/70">{data.model_used}</span>
        </div>
      </div>
    </div>
  );
}
