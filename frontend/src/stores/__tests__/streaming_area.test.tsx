import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { useAgentStore } from "@/stores/agent";
import type { AgentMessage } from "@/types/agent";

/**
 * Extracted streaming area component matching Agent.tsx structure.
 * Isolates the DOM structure for testing without the full Agent page.
 */
function StreamingArea() {
  const status = useAgentStore((s) => s.status);
  const streamingText = useAgentStore((s) => s.streamingText);
  const toolCalls = useAgentStore((s) => s.toolCalls);
  const messages = useAgentStore((s) => s.messages);

  const reasoningActive = streamingText.startsWith("Thinking:");

  if (status !== "streaming") return null;

  return (
    <div data-testid="streaming-wrapper">
      <div className="flex gap-3">
        <div data-testid="avatar">A</div>
        <div className="flex-1 min-w-0 space-y-1.5">
          {!reasoningActive && !streamingText && toolCalls.length === 0 && !messages.some((m: AgentMessage) => m.type === "swarm_status") && (
            <div data-testid="placeholder">
              <span>Agent working...</span>
            </div>
          )}
          {reasoningActive && !streamingText && (
            <div data-testid="reasoning">
              <span>Reasoning...</span>
            </div>
          )}
          {streamingText && (
            <div data-testid="streaming-text">
              {streamingText}
              <span data-testid="cursor" />
            </div>
          )}
          {toolCalls.length > 0 && (
            <div data-testid="tool-progress">
              {toolCalls.map((tc) => (
                <span key={tc.id} data-testid={`tool-${tc.id}`}>{tc.tool}</span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

beforeEach(() => {
  useAgentStore.getState().reset();
});

describe("StreamingArea — DOM stability during state transitions", () => {
  it("renders placeholder when streaming starts with no content", () => {
    act(() => {
      useAgentStore.getState().setSessionId("s1");
      useAgentStore.getState().setStatus("streaming");
    });

    render(<StreamingArea />);
    expect(screen.getByTestId("streaming-wrapper")).toBeInTheDocument();
    expect(screen.getByTestId("placeholder")).toBeInTheDocument();
  });

  it("wrapper stays in DOM when placeholder transitions to streaming text", () => {
    act(() => {
      useAgentStore.getState().setSessionId("s1");
      useAgentStore.getState().setStatus("streaming");
    });

    render(<StreamingArea />);
    const wrapper = screen.getByTestId("streaming-wrapper");

    // Placeholder visible initially
    expect(screen.getByTestId("placeholder")).toBeInTheDocument();

    // Transition: append delta → placeholder disappears, text appears
    act(() => {
      useAgentStore.getState().appendDelta("Hello");
    });

    // Wrapper must still be the same DOM node
    expect(screen.getByTestId("streaming-wrapper")).toBe(wrapper);
    expect(screen.queryByTestId("placeholder")).not.toBeInTheDocument();
    expect(screen.getByTestId("streaming-text")).toBeInTheDocument();
    expect(screen.getByTestId("streaming-text")).toHaveTextContent("Hello");
  });

  it("wrapper stays in DOM when text transitions to include tool calls", () => {
    act(() => {
      useAgentStore.getState().setSessionId("s1");
      useAgentStore.getState().setStatus("streaming");
      useAgentStore.getState().appendDelta("Analyzing...");
    });

    render(<StreamingArea />);
    const wrapper = screen.getByTestId("streaming-wrapper");

    act(() => {
      useAgentStore.getState().addToolCall({
        id: "tc-1",
        tool: "run_backtest",
        arguments: {},
        status: "running",
        timestamp: Date.now(),
      });
    });

    expect(screen.getByTestId("streaming-wrapper")).toBe(wrapper);
    expect(screen.getByTestId("streaming-text")).toBeInTheDocument();
    expect(screen.getByTestId("tool-progress")).toBeInTheDocument();
    expect(screen.getByTestId("tool-tc-1")).toHaveTextContent("run_backtest");
  });

  it("no insertBefore error during rapid reasoning→text→tools transition", () => {
    const errors: Error[] = [];
    const originalInsertBefore = Node.prototype.insertBefore;
    Node.prototype.insertBefore = function (...args: Parameters<typeof originalInsertBefore>) {
      try {
        return originalInsertBefore.apply(this, args);
      } catch (e) {
        errors.push(e as Error);
        throw e;
      }
    };

    act(() => {
      useAgentStore.getState().setSessionId("s1");
      useAgentStore.getState().setStatus("streaming");
    });

    render(<StreamingArea />);

    // Rapid state transitions
    act(() => {
      useAgentStore.getState().appendDelta("Thinking: analyzing data");
    });

    act(() => {
      useAgentStore.getState().clearStreaming();
      useAgentStore.getState().appendDelta("The result is 42");
    });

    act(() => {
      useAgentStore.getState().addToolCall({
        id: "tc-1",
        tool: "web_search",
        arguments: {},
        status: "running",
        timestamp: Date.now(),
      });
    });

    act(() => {
      useAgentStore.getState().updateToolCall("tc-1", {
        status: "ok",
        elapsed_ms: 300,
      });
    });

    act(() => {
      useAgentStore.getState().clearStreaming();
      useAgentStore.getState().appendDelta("Final answer after tools.");
    });

    // No insertBefore errors
    expect(errors).toHaveLength(0);
    expect(screen.getByTestId("streaming-text")).toHaveTextContent("Final answer after tools.");

    Node.prototype.insertBefore = originalInsertBefore;
  });

  it("wrapper unmounts cleanly when streaming ends", () => {
    act(() => {
      useAgentStore.getState().setSessionId("s1");
      useAgentStore.getState().setStatus("streaming");
      useAgentStore.getState().appendDelta("text");
    });

    render(<StreamingArea />);
    expect(screen.getByTestId("streaming-wrapper")).toBeInTheDocument();

    act(() => {
      useAgentStore.getState().clearStreaming();
      useAgentStore.getState().setStatus("idle");
    });

    expect(screen.queryByTestId("streaming-wrapper")).not.toBeInTheDocument();
  });

  it("stream_reset clears text but keeps wrapper mounted", () => {
    act(() => {
      useAgentStore.getState().setSessionId("s1");
      useAgentStore.getState().setStatus("streaming");
      useAgentStore.getState().appendDelta("partial");
    });

    render(<StreamingArea />);
    const wrapper = screen.getByTestId("streaming-wrapper");

    act(() => {
      useAgentStore.getState().clearStreaming();
    });

    expect(screen.getByTestId("streaming-wrapper")).toBe(wrapper);
    expect(screen.queryByTestId("streaming-text")).not.toBeInTheDocument();
    expect(screen.getByTestId("placeholder")).toBeInTheDocument();
  });
});
