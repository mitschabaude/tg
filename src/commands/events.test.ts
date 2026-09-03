import assert from "node:assert/strict";
import test from "node:test";
import { formatEvent, type ListenerRow } from "./events.ts";

function listenerRow(kind: ListenerRow["kind"]): ListenerRow {
  return {
    kind,
    chat: {
      peer_id: -1002667675993,
      title: "clean",
      username: null,
    },
    message: {
      id: 400,
      date: "2026-08-05T15:20:00+00:00",
      sender_id: 7093672513,
      sender_title: "Nicolas Schleicher",
      sender_username: "nicolas_schleicher",
      fwd_from_peer_id: null,
      fwd_from_title: null,
      fwd_from_username: null,
      fwd_from_name: null,
      fwd_date: null,
      fwd_channel_post: null,
      fwd_post_author: null,
      fwd_saved_from_peer_id: null,
      fwd_saved_from_title: null,
      fwd_saved_from_username: null,
      fwd_saved_from_msg_id: null,
      text: "I may open a PR once this becomes a blocker.",
      out: false,
      post: false,
      reply_to_msg_id: null,
      attachments: [{
        index: 0,
        kind: "MessageMediaWebPage",
        name: null,
        mime_type: null,
        size: null,
        ext: null,
        file_id: null,
        width: null,
        height: null,
        duration: null,
        path: null,
        downloaded: false,
        download_skipped: "no_file",
        download_error: null,
        path_source: null,
      }],
      reaction_counts: [],
      recent_reactions: [],
      reactions_complete: false,
    },
  };
}

test("message events contain only a concise id and body", () => {
  const event = formatEvent(listenerRow("message"));

  assert.deepEqual(Object.keys(event), ["id", "body"]);
  assert.equal(event.id, "tg/message/-1002667675993/400");
  assert.match(event.body, /Telegram message\nChat: clean \[-1002667675993\]/);
  assert.match(event.body, /Nicolas Schleicher \(@nicolas_schleicher\)/);
  assert.match(event.body, /I may open a PR once this becomes a blocker\./);
  assert.match(event.body, /tg messages list --chat -1002667675993 --limit 20/);
  assert.doesNotMatch(event.body, /sender_id|fwd_from|reaction_counts|"out"/);
  assert.doesNotMatch(event.body, /MessageMediaWebPage|download_skipped/);
});

test("message events identify outgoing messages", () => {
  const row = listenerRow("message");
  row.message.out = true;

  const event = formatEvent(row);

  assert.match(event.body, /^Outgoing Telegram message\n/);
});

test("message events do not wrap long message text", () => {
  const row = listenerRow("message");
  row.message.text = "This message deliberately contains enough words to exceed the terminal formatter width without introducing line breaks in an event body.";

  const event = formatEvent(row);

  assert.ok(event.body.includes(row.message.text));
});

test("reaction events identify an empty current state", () => {
  const event = formatEvent(listenerRow("reaction"));

  assert.match(event.id, /^tg\/reaction\/-1002667675993\/400\/[0-9a-f]{16}$/);
  assert.match(event.body, /Telegram reaction update/);
  assert.match(event.body, /Current reactions: none/);
});
