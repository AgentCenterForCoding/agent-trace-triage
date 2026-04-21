// Variant C — per-row expand-to-detail (no top widgets)
// Each row reveals an inline drawer with the full triage/analysis view.

function TraceListV3() {
  const [expanded, setExpanded] = React.useState('trc_8f3a21c4');
  const rows = TRACES;
  const maxLat = Math.max(...TRACES.map(t => t.latency));

  const segmentsFor = (t) => {
    if (t.err === 'ToolTimeout')      return [{kind:'plan',w:0.04},{kind:'llm',w:0.12},{kind:'tool',w:0.65,err:true},{kind:'llm',w:0.19}];
    if (t.err === 'Hallucination')    return [{kind:'plan',w:0.05},{kind:'llm',w:0.22},{kind:'tool',w:0.18},{kind:'llm',w:0.30},{kind:'tool',w:0.25,err:true}];
    if (t.err === 'SchemaMismatch')   return [{kind:'plan',w:0.06},{kind:'llm',w:0.30},{kind:'tool',w:0.22,err:true},{kind:'llm',w:0.42}];
    if (t.err === 'MaxStepsReached')  return Array.from({length:10},(_,i)=>({kind:i%2===0?'llm':'tool',w:0.1,err:i===9}));
    if (t.err === 'LoopDetected')     return Array.from({length:8},(_,i)=>({kind:'tool',w:0.125,err:i>=5}));
    return [{kind:'plan',w:0.08},{kind:'llm',w:0.34},{kind:'tool',w:0.18},{kind:'llm',w:0.40}];
  };

  const segColor = (s) => s.err ? T.red : s.kind==='llm'?T.accent : s.kind==='tool'?'oklch(0.72 0.10 195)' : T.green;

  return (
    <div style={{
      width:'100%', height:'100%', background:T.bg, color:T.text,
      display:'flex', flexDirection:'column', overflow:'hidden', fontSize:13,
    }}>
      {/* Top bar */}
      <div style={{
        display:'flex', alignItems:'center', gap:12,
        padding:'12px 20px', borderBottom:`1px solid ${T.border}`,
        height:52, flexShrink:0, background:T.surface,
      }}>
        <span style={{fontSize:15, fontWeight:600, letterSpacing:-0.2}}>问题定界 <span style={{color:T.textMute, fontWeight:400}}>· Triage</span></span>
        <span className="mono" style={{padding:'2px 6px', borderRadius:2, background:T.surface2, color:T.textDim, fontSize:11, border:`1px solid ${T.border}`}}>prod</span>
        <div style={{flex:1}} />
        <div style={{display:'flex', border:`1px solid ${T.border}`, borderRadius:3, overflow:'hidden'}}>
          {['15m','1h','6h','24h','7d'].map((r,i)=>(
            <span key={r} style={{
              padding:'5px 10px', fontSize:11.5, cursor:'pointer',
              background: r==='1h' ? T.accentDim : 'transparent',
              color: r==='1h' ? T.text : T.textDim,
              borderRight: i<4 ? `1px solid ${T.border}` : 'none',
            }}>{r}</span>
          ))}
        </div>
        <span style={{padding:'5px 10px', fontSize:11.5, color:T.textDim, border:`1px solid ${T.border}`, borderRadius:3, display:'inline-flex', alignItems:'center', gap:5}}>
          <Icon.Refresh/> auto
        </span>
      </div>

      {/* Filter rail */}
      <div style={{
        display:'flex', alignItems:'center', gap:8,
        padding:'10px 20px', borderBottom:`1px solid ${T.border}`,
        background:T.surface2, flexShrink:0,
      }}>
        <Icon.Filter style={{color:T.textDim}} />
        <Chip active>status:error</Chip>
        <Chip active>agent:sales-copilot-v2</Chip>
        <Chip active>latency:&gt;5s</Chip>
        <Chip>+ add filter</Chip>
        <div style={{flex:1}} />
        <span style={{fontSize:11.5, color:T.textDim}}>
          sort by <span className="mono" style={{color:T.text}}>latency desc</span> <Icon.Chevron />
        </span>
        <span style={{fontSize:11.5, color:T.textDim}}>
          <span className="mono" style={{color:T.text}}>{rows.length}</span> traces
        </span>
      </div>

      {/* Column headers */}
      <div style={{
        display:'grid', gridTemplateColumns:'14px 14px 96px 140px 1fr 70px 46px',
        alignItems:'center', gap:14, padding:'6px 20px',
        fontSize:10.5, color:T.textMute, textTransform:'uppercase', letterSpacing:0.6,
        borderBottom:`1px solid ${T.border}`, background:T.surface, flexShrink:0,
      }}>
        <span />
        <span />
        <span>trace</span>
        <span>agent · error</span>
        <span>waterfall</span>
        <span style={{textAlign:'right'}}>latency</span>
        <span style={{textAlign:'right'}}>steps</span>
      </div>

      {/* Rows */}
      <div style={{flex:1, overflow:'auto'}}>
        {rows.map((t) => {
          const isOpen = t.id === expanded;
          const segs = segmentsFor(t);
          const widthPct = (t.latency / maxLat) * 100;
          return (
            <React.Fragment key={t.id}>
              <div onClick={() => setExpanded(isOpen ? null : t.id)}
                style={{
                  display:'grid',
                  gridTemplateColumns:'14px 14px 96px 140px 1fr 70px 46px',
                  alignItems:'center', gap:14,
                  padding:'12px 20px',
                  borderBottom: isOpen ? `1px solid ${T.border}` : `1px solid ${T.borderSoft}`,
                  background: isOpen ? T.accentDim : 'transparent',
                  cursor:'pointer',
                }}>
                <span style={{
                  color: T.textDim, display:'inline-flex', alignItems:'center', justifyContent:'center',
                  transition:'transform .15s', transform: isOpen ? 'rotate(0deg)' : 'rotate(-90deg)',
                }}>
                  <Icon.Chevron />
                </span>
                <StatusDot status={t.status} />
                <span className="mono" style={{fontSize:11, color:T.text}}>{t.id.slice(4,12)}</span>
                <div style={{minWidth:0}}>
                  <div className="mono" style={{fontSize:11, color:T.textDim, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>{t.agent}</div>
                  {t.err
                    ? <div className="mono" style={{fontSize:11, color:T.red, marginTop:2}}>{t.err}</div>
                    : <div style={{fontSize:11, color:T.green, marginTop:2}}>ok</div>}
                </div>
                <div style={{minWidth:0}}>
                  <div style={{fontSize:12, color:T.text, marginBottom:5, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>{t.task}</div>
                  <div style={{
                    height:10, display:'flex', borderRadius:2, overflow:'hidden',
                    width:`${widthPct}%`, minWidth:80, background:T.border,
                  }}>
                    {segs.map((s,i)=>(
                      <div key={i} title={s.kind+(s.err?' (error)':'')}
                        style={{
                          width:`${s.w*100}%`, height:'100%', background: segColor(s),
                          borderRight: i<segs.length-1 ? `1px solid ${T.bg}` : 'none',
                          opacity: s.err ? 1 : 0.85,
                        }} />
                    ))}
                  </div>
                </div>
                <span className="mono" style={{fontSize:12, color:T.text, fontVariantNumeric:'tabular-nums', textAlign:'right'}}>{fmtMs(t.latency)}</span>
                <span className="mono" style={{fontSize:11, color:T.textDim, fontVariantNumeric:'tabular-nums', textAlign:'right'}}>{t.steps}</span>
              </div>
              {isOpen && <TraceRowDrawer trace={t} />}
            </React.Fragment>
          );
        })}
      </div>

      {/* Legend footer */}
      <div style={{
        padding:'8px 20px', borderTop:`1px solid ${T.border}`, background:T.surface,
        display:'flex', alignItems:'center', gap:16, fontSize:11, color:T.textDim, flexShrink:0,
      }}>
        <span>Legend</span>
        {[['LLM',T.accent],['Tool','oklch(0.72 0.10 195)'],['Plan',T.green],['Error',T.red]].map(([n,c])=>(
          <span key={n} style={{display:'inline-flex', alignItems:'center', gap:5}}>
            <span style={{width:10, height:10, background:c, borderRadius:1}} />
            {n}
          </span>
        ))}
        <div style={{flex:1}} />
        <span className="mono">row width ∝ latency · segment width ∝ phase share · click row to expand</span>
      </div>
    </div>
  );
}

// Inline expandable drawer: full analysis for one trace.
function TraceRowDrawer({ trace }) {
  // Build step-level timeline
  const buildSteps = (t) => {
    if (t.err === 'ToolTimeout') return [
      { t:0,    dur:420,  kind:'plan', name:'agent.plan',                             detail:'决策: 需要查询客户续约数据 → 调 crm.getAccount' },
      { t:420,  dur:8000, kind:'tool', name:'tool: crm.getAccount',        err:true,  detail:'account_id="acct_921" · deadline 8000ms → 504 Gateway Timeout' },
      { t:8420, dur:1820, kind:'llm',  name:'llm.stream (gpt-4o)',                    detail:'尝试从错误中恢复 · 生成"稍后重试"兜底文案' },
      { t:10240,dur:860,  kind:'tool', name:'tool: email.draft',                      detail:'subject="关于 ACME 续约 · 状态待确认"' },
      { t:11100,dur:1740, kind:'llm',  name:'llm.stream (gpt-4o)',                    detail:'产出最终回复给用户' },
    ];
    if (t.err === 'Hallucination') return [
      { t:0,    dur:380,  kind:'plan', name:'agent.plan',                             detail:'决策: 在 KB 中搜索登录相关条目' },
      { t:380,  dur:1540, kind:'llm',  name:'llm.stream',                             detail:'推理需要引用具体 KB 编号' },
      { t:1920, dur:1260, kind:'tool', name:'tool: kb.search',                        detail:'query="login failed 2FA" → 返回 5 条相似条目' },
      { t:3180, dur:2100, kind:'llm',  name:'llm.stream',                             detail:'生成回复中引用了不存在的 KB-9912' },
      { t:5280, dur:1740, kind:'tool', name:'tool: kb.fetch',            err:true,    detail:'kb_id="KB-9912" → 404 Not Found · agent 未自检' },
    ];
    return [
      { t:0, dur:t.latency*0.05, kind:'plan', name:'agent.plan', detail:'任务规划' },
      { t:t.latency*0.05, dur:t.latency*0.40, kind:'llm', name:'llm.stream', detail:'推理步骤' },
      { t:t.latency*0.45, dur:t.latency*0.20, kind:'tool', name:'tool call', detail:'工具调用' },
      { t:t.latency*0.65, dur:t.latency*0.35, kind:'llm', name:'llm.stream', detail:'生成最终回复' },
    ];
  };
  const steps = buildSteps(trace);
  const total = trace.latency;
  const stepColor = (s) => s.err ? T.red : s.kind==='llm'?T.accent : s.kind==='tool'?'oklch(0.72 0.10 195)' : T.green;

  return (
    <div style={{
      borderBottom:`1px solid ${T.border}`,
      background:T.surface,
      padding:'0 0 0 48px',
    }}>
      <div style={{
        display:'grid', gridTemplateColumns:'1fr 320px', gap:0,
      }}>
        {/* Left: timeline + reasoning */}
        <div style={{padding:'16px 22px 18px', borderRight:`1px solid ${T.border}`, minWidth:0}}>
          {/* Error banner */}
          {trace.err && (
            <div style={{
              background:'rgba(220,80,80,0.06)', border:`1px solid ${T.redDim}`,
              borderRadius:3, padding:'10px 12px', marginBottom:14,
            }}>
              <div style={{display:'flex', alignItems:'center', gap:8, marginBottom:5}}>
                <span className="mono" style={{
                  fontSize:10.5, padding:'1px 6px', borderRadius:2,
                  background:T.redDim, color:T.red, fontWeight:600,
                }}>{trace.err}</span>
                <span style={{fontSize:10.5, color:T.textMute}}>
                  同根问题 · <span className="mono" style={{color:T.textDim}}>cluster c01 · 47 similar</span>
                </span>
                <div style={{flex:1}} />
                <span style={{fontSize:11, color:T.accent, cursor:'pointer'}}>查看归因 →</span>
              </div>
              <div className="mono" style={{fontSize:11.5, color:T.text, lineHeight:1.5}}>{trace.errMsg}</div>
            </div>
          )}

          {/* Step-level timeline */}
          <div style={{display:'flex', alignItems:'center', gap:8, marginBottom:10}}>
            <span style={{fontSize:10.5, color:T.textMute, textTransform:'uppercase', letterSpacing:0.6}}>分析过程 · step timeline</span>
            <div style={{flex:1, height:1, background:T.borderSoft}} />
            <span className="mono" style={{fontSize:10.5, color:T.textMute}}>
              {fmtMs(total)} · {steps.length} steps · {trace.tools} tool calls
            </span>
          </div>

          {/* Axis */}
          <div style={{display:'grid', gridTemplateColumns:'210px 1fr 56px', gap:10, fontSize:10, color:T.textMute, marginBottom:4}}>
            <span />
            <div style={{display:'flex', justifyContent:'space-between'}}>
              <span className="mono">0s</span>
              <span className="mono">{fmtMs(total*0.5)}</span>
              <span className="mono">{fmtMs(total)}</span>
            </div>
            <span />
          </div>

          {/* Steps */}
          {steps.map((s, i) => (
            <div key={i} style={{
              display:'grid', gridTemplateColumns:'210px 1fr 56px',
              alignItems:'center', gap:10,
              padding:'7px 0',
              borderTop: i===0 ? `1px dashed ${T.borderSoft}` : 'none',
              borderBottom: `1px dashed ${T.borderSoft}`,
            }}>
              <div style={{minWidth:0}}>
                <div style={{display:'flex', alignItems:'center', gap:6}}>
                  <span className="mono" style={{fontSize:9.5, color:T.textMute, width:18}}>#{String(i+1).padStart(2,'0')}</span>
                  <span style={{width:6, height:6, borderRadius:1, background:stepColor(s), flexShrink:0}} />
                  <span className="mono" style={{
                    fontSize:11.5, color: s.err ? T.red : T.text, fontWeight:500,
                    overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
                  }}>{s.name}</span>
                </div>
                <div style={{
                  fontSize:11, color:T.textDim, marginTop:3, paddingLeft:30,
                  overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
                }}>{s.detail}</div>
              </div>
              <div style={{position:'relative', height:16}}>
                <div style={{
                  position:'absolute', inset:'0 0 0 0', top:6, height:4,
                  background:T.border, borderRadius:1,
                }} />
                <div style={{
                  position:'absolute', height:4, top:6, borderRadius:1,
                  left:`${(s.t/total)*100}%`,
                  width:`${(s.dur/total)*100}%`,
                  background: stepColor(s),
                  boxShadow: s.err ? `0 0 0 2px rgba(220,80,80,0.2)` : 'none',
                }} />
              </div>
              <span className="mono" style={{
                fontSize:10.5, color:T.textMute, textAlign:'right', fontVariantNumeric:'tabular-nums',
              }}>{fmtMs(s.dur)}</span>
            </div>
          ))}

          {/* Input / output preview */}
          <div style={{marginTop:16, display:'grid', gridTemplateColumns:'1fr 1fr', gap:10}}>
            <CodeBlock label="user input" body={trace.task} />
            <CodeBlock label={trace.err ? 'final response (fallback)' : 'final response'}
              tone={trace.err ? 'warn' : 'ok'}
              body={trace.err === 'ToolTimeout'
                ? '"您好，正在为您查询 ACME 续约信息，系统当前繁忙，我稍后会把报价邮件草稿发给您。"'
                : trace.err === 'Hallucination'
                ? '"请参考知识库 KB-9912…" (引用的条目不存在)'
                : '"好的，已为您整理本季度即将到期的 12 份合同…"'
              } />
          </div>
        </div>

        {/* Right: hypothesis + actions */}
        <div style={{padding:'16px 22px'}}>
          {trace.err && (
            <div style={{marginBottom:16}}>
              <div style={{display:'flex', alignItems:'center', gap:6, marginBottom:8}}>
                <span style={{fontSize:10.5, color:T.textMute, textTransform:'uppercase', letterSpacing:0.6}}>疑似根因</span>
                <span className="mono" style={{fontSize:9.5, color:T.accent, padding:'1px 5px', background:T.accentDim, borderRadius:2}}>AUTO</span>
              </div>
              <div style={{fontSize:12, color:T.text, lineHeight:1.6}}>
                Step #2 工具调用 <span className="mono" style={{color:T.red}}>crm.getAccount</span> 在
                <span className="mono" style={{color:T.red}}> 8.0s</span> deadline 命中前返回 504。
                上游 <span className="mono" style={{color:T.text}}>warehouse.read</span> p95 自
                <span className="mono" style={{color:T.text}}> deploy@v3.12</span> 起由 2.1s → 9.4s。
              </div>
            </div>
          )}

          <div style={{marginBottom:16}}>
            <div style={{fontSize:10.5, color:T.textMute, textTransform:'uppercase', letterSpacing:0.6, marginBottom:8}}>上下文</div>
            <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', rowGap:6, columnGap:10, fontSize:11}}>
              {[
                ['model', trace.model],
                ['env',   trace.env],
                ['user',  trace.user],
                ['trigger', trace.trigger],
                ['turns', trace.turns],
                ['cost',  fmtCost(trace.cost)],
                ['tokens', fmtK(trace.tokens)],
                ['started', trace.startedAt],
              ].map(([k,v])=>(
                <div key={k} style={{display:'flex', justifyContent:'space-between', gap:8}}>
                  <span className="mono" style={{color:T.textMute}}>{k}</span>
                  <span className="mono" style={{color:T.text, fontVariantNumeric:'tabular-nums', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>{v}</span>
                </div>
              ))}
            </div>
          </div>

          <div style={{marginBottom:16}}>
            <div style={{fontSize:10.5, color:T.textMute, textTransform:'uppercase', letterSpacing:0.6, marginBottom:8}}>标签</div>
            <div style={{display:'flex', flexWrap:'wrap', gap:6}}>
              {trace.tags.map(tag => <Chip key={tag} tone="ghost">{tag}</Chip>)}
            </div>
          </div>

          <div style={{display:'flex', flexDirection:'column', gap:6}}>
            <ActionBtn primary>在 Trace 查看器中打开</ActionBtn>
            <ActionBtn>对比成功 trace</ActionBtn>
            <ActionBtn>分派给 @tooling-team</ActionBtn>
            <ActionBtn>加入测试集</ActionBtn>
          </div>
        </div>
      </div>
    </div>
  );
}

function CodeBlock({ label, body, tone = 'default' }) {
  const borderColor = tone === 'warn' ? T.amber : tone === 'ok' ? T.borderSoft : T.borderSoft;
  return (
    <div>
      <div style={{fontSize:10, color:T.textMute, textTransform:'uppercase', letterSpacing:0.5, marginBottom:5}}>{label}</div>
      <div className="mono" style={{
        fontSize:11, color:T.text, lineHeight:1.5,
        background:T.bg, border:`1px solid ${borderColor}`, borderRadius:2,
        padding:'8px 10px', minHeight:42,
      }}>{body}</div>
    </div>
  );
}

function ActionBtn({ children, primary }) {
  return (
    <span style={{
      padding:'6px 10px', fontSize:11.5, borderRadius:3, textAlign:'center',
      cursor:'pointer',
      background: primary ? T.accentDim : T.bg,
      border: `1px solid ${primary ? T.accent : T.border}`,
      color: primary ? T.text : T.textDim,
    }}>{children}</span>
  );
}

Object.assign(window, { TraceListV3 });
