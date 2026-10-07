import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";

/* ---------------------------------- types --------------------------------- */

type NavId = "history" | "demo" | "theme" | "letter" | "night" | "motion" | "still" | "paint";

type NavItem = {
  id: NavId;
  label: string;
  hint: string;
  icon: ReactNode;
};

type MoodTag = "低落" | "焦虑" | "平静" | "感恩" | "期待" | "疲惫";

type ChatRole = "agent" | "user";

type ChatMessage = {
  id: string;
  role: ChatRole;
  text: string;
  time: string;
  note?: boolean;
};

type Pane = "write" | "talk";

/* ---------------------------------- icons --------------------------------- */

const iconProps = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

function Icon({ children, size = 19 }: { children: ReactNode; size?: number }) {
  return (
    <svg {...iconProps} width={size} height={size}>
      {children}
    </svg>
  );
}

const navItems: NavItem[] = [
  {
    id: "history",
    label: "历史",
    hint: "过往的日子",
    icon: (
      <Icon>
        <path d="M3.5 9.5A8.5 8.5 0 1 1 12 20.5a8.5 8.5 0 0 1-7.6-4.7" />
        <path d="M3.2 4.2v3.6h3.6M12 7.6V12l3.2 1.9" />
      </Icon>
    ),
  },
  {
    id: "demo",
    label: "演示",
    hint: "看一看它怎么陪",
    icon: (
      <Icon>
        <path d="M12 3.2 20 7.6v8.8L12 20.8 4 16.4V7.6z" />
        <path d="M4 7.6l8 4.4 8-4.4M12 12v8.8" />
      </Icon>
    ),
  },
  {
    id: "theme",
    label: "主题",
    hint: "纸的温度",
    icon: (
      <Icon>
        <path d="M12 3.4a8.6 8.6 0 1 0 0 17.2c1.4 0 2-.9 2-1.9s-.7-1.7-.7-2.6c0-1 .8-1.8 1.9-1.8h1.7c1.5 0 2.7-1.2 2.7-2.7C19.6 6.9 16.3 3.4 12 3.4z" />
        <circle cx="8.3" cy="9" r=".9" fill="currentColor" stroke="none" />
        <circle cx="12" cy="7.4" r=".9" fill="currentColor" stroke="none" />
        <circle cx="15.6" cy="9.2" r=".9" fill="currentColor" stroke="none" />
        <circle cx="8" cy="13.4" r=".9" fill="currentColor" stroke="none" />
      </Icon>
    ),
  },
  {
    id: "letter",
    label: "信笺",
    hint: "此刻写下来",
    icon: (
      <Icon>
        <path d="M4 6.6h16v10.8H4z" />
        <path d="M4.6 7.2 12 12.6l7.4-5.4" />
      </Icon>
    ),
  },
  {
    id: "night",
    label: "夜笺",
    hint: "睡前说给自己",
    icon: (
      <Icon>
        <path d="M20 14.4A8.4 8.4 0 0 1 9.6 4a8.4 8.4 0 1 0 10.4 10.4z" />
      </Icon>
    ),
  },
  {
    id: "motion",
    label: "动效",
    hint: "纸的呼吸",
    icon: (
      <Icon>
        <path d="M12 3.6l1.7 4.3 4.3 1.7-4.3 1.7L12 15.6l-1.7-4.3L6 9.6l4.3-1.7z" />
        <path d="M18.4 15.4l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" />
      </Icon>
    ),
  },
  {
    id: "still",
    label: "静",
    hint: "什么都不做",
    icon: (
      <Icon>
        <circle cx="12" cy="12" r="8.4" />
        <circle cx="12" cy="12" r="3.2" />
      </Icon>
    ),
  },
  {
    id: "paint",
    label: "画",
    hint: "涂一点颜色",
    icon: (
      <Icon>
        <path d="M15.4 4.6l4 4-8.4 8.4H7v-4z" />
        <path d="M13.6 6.4l4 4" />
        <path d="M5.4 20.2h13.2" />
      </Icon>
    ),
  },
];

const moodPalette: MoodTag[] = ["低落", "焦虑", "平静", "感恩", "期待", "疲惫"];

/* -------------------------------- constants ------------------------------- */

const STORAGE_JOURNAL = "man-ye.journal.v3";
const STORAGE_CHAT = "man-ye.chat.v3";
const RATING_TOTAL = 10;

const initialChat: ChatMessage[] = [
  {
    id: "c1",
    role: "agent",
    note: true,
    time: "21:46",
    text: "它刚翻阅过你近几天的日记，想先陪你坐一会儿，再听你说今天。",
  },
  {
    id: "c2",
    role: "agent",
    time: "21:47",
    text: "我看你这两天都睡得很晚，昨天一整天也过得有些空。今天想跟我说说发生了什么吗？不想说也没关系，我在。",
  },
  { id: "c3", role: "user", time: "21:49", text: "今天开会被否了，方案改了三版还是不行。" },
];

const agentReplies: { match: RegExp; lines: string[] }[] = [
  {
    match: /(否定|被否|批评|不行|评了|当众|方案|开会|工作|上班|老板|领导)/,
    lines: [
      "被否掉的是那一版方案，不是你这个人。这两件事，我想再帮你分清楚一次。",
      "改到第三版还是不行，那种无力感我大概能明白。要不要先把它放在这儿，我们聊点别的？",
      "会上被当众评方案，换成谁都会难受一会儿。你现在最想被理解的是哪一部分？",
    ],
  },
  {
    match: /(累|疲惫|困|撑不住|想睡|熬夜|很晚|睡不好|头疼|难受|身体)/,
    lines: [
      "听起来身体已经在求救了。今晚要不要什么都不做，只是躺着？我陪你待一会儿。",
      "累的时候还要责怪自己不够努力，太残忍了。今天到此为止，可以吗？",
    ],
  },
  {
    match: /(开心|高兴|不错|很好|幸运|谢谢|温暖|欣慰|松弛|轻松)/,
    lines: [
      "听你这么说，我也跟着松了一口气。这样的时刻值得被多写两行。",
      "真好。你有没有想过，三年前的自己会怎么看待今天的这件事？",
    ],
  },
  {
    match: /(一个人|孤独|没人|寂寞|孤单|没有意义|空|虚无|不知道)/,
    lines: [
      "那种空落落的感觉，不一定是出了什么问题。也许只是太久没有人好好听你说话了。",
      "此刻这里只有我们两个人。你不用说得完整，说一点点也可以。",
    ],
  },
];

const fallbackReplies = [
  "我在这儿，你慢慢说。不用组织好语言，也不用先想清楚。",
  "谢谢你愿意告诉我。如果我们把它写进今天的信笺，你会想用哪几个字开头？",
  "嗯，我在听。还有吗？",
  "有些事现在说不明白也没关系。我先陪你把它放在这儿。",
];

/* -------------------------------- utilities ------------------------------- */

function nowTime() {
  const date = new Date();
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function todayLabel() {
  const date = new Date();
  const weekMap = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];
  return {
    date: `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, "0")}.${String(date.getDate()).padStart(2, "0")}`,
    week: weekMap[date.getDay()],
  };
}

function loadStored<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function store(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage blocked — keep the session working */
  }
}

/* --------------------------------- component ------------------------------ */

export default function App() {
  const today = useMemo(todayLabel, []);
  const [nav, setNav] = useState<NavId>("letter");
  const [pane, setPane] = useState<Pane>("write");

  /* journal */
  const [draft, setDraft] = useState(() =>
    loadStored(STORAGE_JOURNAL, {
      text: "",
      savedText: "",
      savedTime: "",
      moods: [] as MoodTag[],
      rating: 0,
      favorite: false,
    }),
  );
  const [isSaving, setIsSaving] = useState(false);
  const [toolHint, setToolHint] = useState("");

  /* chat */
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadStored(STORAGE_CHAT, initialChat));
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);

  const composerRef = useRef<HTMLTextAreaElement>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);
  const streamRef = useRef<HTMLDivElement>(null);
  const timers = useRef<number[]>([]);

  useEffect(() => () => timers.current.forEach(window.clearTimeout), []);

  const autoGrow = (element: HTMLTextAreaElement | null) => {
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 260)}px`;
  };

  useEffect(() => {
    autoGrow(draftRef.current);
  }, [draft.text]);

  useEffect(() => {
    autoGrow(composerRef.current);
  }, [input]);

  useEffect(() => {
    if (streamRef.current) streamRef.current.scrollTop = streamRef.current.scrollHeight;
  }, [messages, typing]);

  useEffect(() => store(STORAGE_CHAT, messages), [messages]);
  useEffect(() => store(STORAGE_JOURNAL, draft), [draft]);

  const charCount = draft.text.replace(/\s/g, "").length;
  const hasSavedToday = draft.savedText.trim().length > 0;
  const energy = hasSavedToday ? draft.rating : 0;

  const saveJournal = useCallback(() => {
    if (!draft.text.trim()) {
      draftRef.current?.focus();
      return;
    }
    setIsSaving(true);
    setDraft((current) => ({
      ...current,
      savedText: current.text,
      savedTime: nowTime(),
    }));
    const timer = window.setTimeout(() => setIsSaving(false), 900);
    timers.current.push(timer);
  }, [draft.text]);

  const toggleMood = (mood: MoodTag) => {
    setDraft((current) => ({
      ...current,
      moods: current.moods.includes(mood)
        ? current.moods.filter((item) => item !== mood)
        : [...current.moods, mood],
    }));
  };

  const setRating = (value: number) => {
    setDraft((current) => ({ ...current, rating: value }));
  };

  const flashToolHint = useCallback((message: string) => {
    setToolHint(message);
    const timer = window.setTimeout(() => setToolHint(""), 2200);
    timers.current.push(timer);
  }, []);

  const pickReply = (text: string) => {
    const rule = agentReplies.find((item) => item.match.test(text));
    const pool = rule ? rule.lines : fallbackReplies;
    return pool[Math.floor(Math.random() * pool.length)];
  };

  const sendMessage = () => {
    const text = input.trim();
    if (!text || typing) return;

    const userMessage: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      text,
      time: nowTime(),
    };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setTyping(true);

    const delay = 700 + Math.min(text.length * 45, 1400);
    const timer = window.setTimeout(() => {
      setMessages((current) => [
        ...current,
        { id: `a-${Date.now()}`, role: "agent", text: pickReply(text), time: nowTime() },
      ]);
      setTyping(false);
    }, delay);
    timers.current.push(timer);
  };

  const onComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className={`app pane-${pane}`}>
      {/* ------------------------------ icon rail ----------------------------- */}
      <aside className="rail">
        <div className="rail-brand" title="低">
          低
        </div>
        <nav className="rail-nav" aria-label="主导航">
          {navItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`rail-item ${nav === item.id ? "is-active" : ""}`}
              onClick={() => setNav(item.id)}
              aria-current={nav === item.id}
              data-hint={item.hint}
            >
              <span className="rail-icon">{item.icon}</span>
              <span className="rail-label">{item.label}</span>
            </button>
          ))}
        </nav>
        <button type="button" className="rail-foot" aria-label="设置">
          <span className="rail-icon">
            <Icon>
              <circle cx="12" cy="12" r="3.1" />
              <path d="M19.3 14.6a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56v.17a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1.11-1.56 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H3.4a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.56-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h.08A1.7 1.7 0 0 0 10.5 3.5V3.4a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v.08a1.7 1.7 0 0 0 1.56 1.03h.17a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.56 1.03z" />
            </Icon>
          </span>
        </button>
      </aside>

      {/* ------------------------------- letter ------------------------------- */}
      <main className="letter">
        <header className="letter-head">
          <div className="letter-heading">
            <h1>今天</h1>
            <p className="letter-date">
              {today.date}
              <span className="letter-week">{today.week}</span>
            </p>
          </div>
          <button
            type="button"
            className={`letter-fav ${draft.favorite ? "is-on" : ""}`}
            onClick={() => setDraft((current) => ({ ...current, favorite: !current.favorite }))}
            aria-label={draft.favorite ? "取消收藏今天" : "收藏今天"}
          >
            <Icon size={17}>
              <path d="M20.3 8.9c0 4-8.3 9.7-8.3 9.7S3.7 12.9 3.7 8.9a4.4 4.4 0 0 1 8.3-2 4.4 4.4 0 0 1 8.3 2z" />
            </Icon>
          </button>
        </header>

        <div className="letter-rule" />

        <section className={`sheet ${isSaving ? "is-saving" : ""}`}>
          <textarea
            ref={draftRef}
            className="sheet-input"
            value={draft.text}
            onChange={(event) => {
              setDraft((current) => ({ ...current, text: event.target.value }));
              autoGrow(event.target);
            }}
            placeholder={"此刻的心情，写下来吧。\n不必完整，也不必写得很好。"}
            aria-label="今天的日记"
          />

          <div className="sheet-foot">
            <div className="sheet-tools">
              <button
                type="button"
                className="tool-btn"
                onClick={() => flashToolHint("贴图还在路上，先把想写的写下来吧。")}
              >
                <span className="tool-plus">＋</span>贴图
              </button>
              {toolHint ? (
                <span className="tool-hint">{toolHint}</span>
              ) : (
                <span className="tool-count">{charCount} 字</span>
              )}
            </div>
            <button type="button" className="save-btn" onClick={saveJournal}>
              {isSaving ? "已记下" : "记录今天"}
            </button>
          </div>
        </section>

        {hasSavedToday && (
          <section className="archive" aria-label="今天已写">
            <div className="archive-head">
              <span className="archive-flag">今天已写</span>
              <span className="archive-time">{draft.savedTime}</span>
            </div>

            <div className="archive-copy">
              {draft.savedText.split("\n").filter(Boolean).map((line, index) => (
                <p key={index}>{line}</p>
              ))}
            </div>

            <div className="archive-meta">
              <div className="mood-tags">
                {draft.moods.length ? (
                  draft.moods.map((mood) => (
                    <span key={mood} className="mood-tag">
                      {mood}
                    </span>
                  ))
                ) : (
                  <>
                    <span className="mood-tag">低落</span>
                    <span className="mood-tag">焦虑</span>
                  </>
                )}
              </div>

              <div className="energy" role="group" aria-label="今天的能量">
                {Array.from({ length: RATING_TOTAL }, (_, index) => (
                  <button
                    key={index}
                    type="button"
                    className={`energy-dot ${index < energy ? "is-on" : ""}`}
                    onClick={() => setRating(index + 1 === energy ? 0 : index + 1)}
                    aria-label={`能量 ${index + 1} / ${RATING_TOTAL}`}
                  />
                ))}
              </div>
            </div>

            <blockquote className="archive-quote">
              —— {draft.moods.includes("低落") || !draft.moods.length
                ? "被否定的一天里，疲惫盖过了委屈。"
                : "今天也好好走完了。"}
            </blockquote>
          </section>
        )}

        <footer className="letter-foot">
          <div className="mood-picker" role="group" aria-label="此刻的心情">
            {moodPalette.map((mood) => (
              <button
                key={mood}
                type="button"
                className={`mood-chip ${draft.moods.includes(mood) ? "is-on" : ""}`}
                onClick={() => toggleMood(mood)}
              >
                {mood}
              </button>
            ))}
          </div>
          <p className="letter-hint">写下的内容只留在这台设备，不会上传。</p>
        </footer>
      </main>

      {/* -------------------------------- companion ------------------------------- */}
      <section className="companion" aria-label="陪伴者对话">
        <header className="companion-head">
          <div className="companion-title">
            <span className="companion-dot" aria-hidden="true" />
            <h2>对话</h2>
          </div>
          <div className="companion-actions">
            <button type="button" className="ghost-btn">
              历史会话
            </button>
            <button
              type="button"
              className="ghost-btn is-strong"
              onClick={() => {
                setMessages([
                  { id: `n-${Date.now()}`, role: "agent", note: true, time: nowTime(), text: "新的唤醒开始了。它重新翻过你的日记，等你开口。" },
                ]);
                setInput("");
              }}
            >
              新的唤醒
            </button>
          </div>
        </header>

        <div className="companion-stream" ref={streamRef}>
          {messages.map((message) => (
            <article key={message.id} className={`msg msg-${message.role} ${message.note ? "is-note" : ""}`}>
              {message.role === "agent" && (
                <div className="msg-avatar" aria-hidden="true">
                  {message.note ? <span className="msg-avatar-eye" /> : <span className="msg-avatar-leaf" />}
                </div>
              )}
              <div className="msg-body">
                {message.note ? (
                  <p className="msg-note">{message.text}</p>
                ) : (
                  <p className="msg-text">{message.text}</p>
                )}
                <span className="msg-time">{message.time}</span>
              </div>
            </article>
          ))}

          {typing && (
            <article className="msg msg-agent is-typing">
              <div className="msg-avatar" aria-hidden="true">
                <span className="msg-avatar-leaf" />
              </div>
              <div className="msg-body">
                <p className="msg-text typing" aria-label="正在输入">
                  <i />
                  <i />
                  <i />
                </p>
              </div>
            </article>
          )}
        </div>

        <footer className="companion-foot">
          <div className="composer">
            <textarea
              ref={composerRef}
              rows={1}
              value={input}
              onChange={(event) => {
                setInput(event.target.value);
                autoGrow(event.target);
              }}
              onKeyDown={onComposerKeyDown}
              placeholder="想说点什么…"
              aria-label="想对陪伴者说的话"
            />
            <button type="button" className="send-btn" onClick={sendMessage} disabled={typing}>
              发送
            </button>
          </div>
          <p className="composer-hint">Enter 发送 · Shift + Enter 换行</p>
        </footer>
      </section>

      {/* ----------------------------- mobile switch ---------------------------- */}
      <div className="pane-switch" role="tablist" aria-label="切换视图">
        <button
          type="button"
          role="tab"
          aria-selected={pane === "write"}
          className={pane === "write" ? "is-on" : ""}
          onClick={() => setPane("write")}
        >
          信笺
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={pane === "talk"}
          className={pane === "talk" ? "is-on" : ""}
          onClick={() => setPane("talk")}
        >
          对话
        </button>
      </div>
    </div>
  );
}
