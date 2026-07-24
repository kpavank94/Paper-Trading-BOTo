import { render } from "@testing-library/react";
import { MessageBubble } from "../MessageBubble";
import type { AgentMessage } from "@/types/agent";

// Unlike MessageBubble.test.tsx, react-markdown is NOT mocked here: these tests
// exercise the real remark-math/rehype-katex pipeline end to end.
vi.mock("../RunCompleteCard", () => ({ RunCompleteCard: () => null }));

function answer(content: string): AgentMessage {
  return { id: "msg-1", type: "answer", content, timestamp: Date.now() };
}

describe("MessageBubble LaTeX rendering", () => {
  it("renders \\(...\\) as KaTeX inline math", () => {
    const { container } = render(
      <MessageBubble msg={answer("Sharpe: \\(\\frac{R_p - R_f}{\\sigma_p}\\)")} />,
    );
    expect(container.querySelector(".katex")).not.toBeNull();
  });

  it("renders \\[...\\] as KaTeX display math", () => {
    const { container } = render(
      <MessageBubble msg={answer("\\[\\sum_{i=1}^n w_i r_i\\]")} />,
    );
    expect(container.querySelector(".katex-display")).not.toBeNull();
  });

  it("renders $$...$$ as KaTeX math", () => {
    const { container } = render(<MessageBubble msg={answer("Vol: $$\\sigma^2$$")} />);
    expect(container.querySelector(".katex")).not.toBeNull();
  });

  it("does NOT treat dollar amounts as math", () => {
    const { container } = render(
      <MessageBubble msg={answer("AAPL fell from $150 to $120 today")} />,
    );
    expect(container.querySelector(".katex")).toBeNull();
    expect(container.textContent).toContain("from $150 to $120");
  });

  it("does NOT transform LaTeX-like text inside code blocks", () => {
    const { container } = render(
      <MessageBubble msg={answer('```python\nre.match(r"\\(x\\)", s)\n```')} />,
    );
    expect(container.querySelector(".katex")).toBeNull();
  });
});
