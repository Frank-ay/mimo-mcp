/**
 * 通用 SSE 流读取工具。
 * 消费一个已成功打开的 fetch Response,按 \n\n 分帧、逐帧解析
 * event:/data: 行,将 (event, parsedData) 交给 dispatch 回调。
 * data JSON parse 失败时静默跳过该帧。
 */
export async function consumeSSE(
  resp: Response,
  dispatch: (event: string, data: unknown) => void,
): Promise<void> {
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    let sep = buf.indexOf("\n\n");
    while (sep !== -1) {
      const raw = buf.slice(0, sep);
      buf = buf.slice(sep + 2);
      sep = buf.indexOf("\n\n");

      let event = "message";
      let data = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;

      try {
        const obj = JSON.parse(data);
        dispatch(event, obj);
      } catch {
        // 忽略 JSON parse 失败的帧,继续读
      }
    }
  }
}
