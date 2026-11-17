// The three Mitu promo reels: copy from F:\MITUai landing page, and the timeline each one plays.
// `node mitu_data.js` prints each reel's length for the motion call.

export const REELS = {
  en: {
    lang: "en", shop: "Nakshi Threads", clock: "3:07", online: "online", typing: "typing…", message: "Message", today: "Today",
    hook: [[{ text: "It's 3 AM." }], [{ text: "14 people just asked " }, { text: "“price?”", accent: true }]],
    chips: ["price?", "is M available?", "delivery charge outside Dhaka?", "COD?", "how much is this one? 📷", "price??",
      "bKash number?", "when will my order arrive?", "L available?", "price pls", "🎤 voice note", "still in stock?", "COD?", "price?"],
    kicker: "Mitu is answering",
    lines: [
      ["them", "price?"],
      ["mitu", "Indigo Block-print Kurti is ৳1,450. Sizes S to XL, 12 left 💙"],
      ["them", "L available? COD outside Dhaka?"],
      ["mitu", "Yes, L is in stock. Delivery outside Dhaka is ৳130, cash on delivery is fine. Total ৳1,580. Shall I place it?"],
      ["them", "yes"],
      ["mitu", "Done ✓ Order #1042 is placed. We’ll message you when it ships."],
    ],
    floats: [[1, "⚡", "Replied in 2 s", "right"], [5, "✓", "Order #1042 · ৳1,580", "left"]],
    end: [[{ text: "Every DM answered." }], [{ text: "Every order taken.", accent: true }]],
    endSub: "Let Mitu take the DMs. You pack the orders.",
    channels: ["WhatsApp", "Messenger", "Instagram", "SMS", "Calls"],
  },
  bn: {
    lang: "bn", shop: "Nakshi Threads", clock: "৩:০৭", online: "অনলাইন", typing: "টাইপ করছে…", message: "মেসেজ", today: "আজ",
    hook: [[{ text: "রাত ৩টা।" }], [{ text: "১৪ জন জিজ্ঞেস করেছে " }, { text: "“দাম কত?”", accent: true }]],
    chips: ["দাম কত?", "M সাইজ আছে?", "ঢাকার বাইরে ডেলিভারি চার্জ কত?", "COD হবে?", "এটার দাম কত? 📷", "দাম??",
      "বিকাশ নম্বর?", "অর্ডার কবে পাব?", "L আছে?", "price pls", "🎤 ভয়েস নোট", "স্টকে আছে?", "COD?", "দাম কত?"],
    kicker: "মিতু উত্তর দিচ্ছে",
    lines: [
      ["them", "দাম কত?"],
      ["mitu", "ইন্ডিগো ব্লক-প্রিন্ট কুর্তি ৳১,৪৫০। সাইজ S থেকে XL, আর ১২টা আছে 💙"],
      ["them", "L আছে? ঢাকার বাইরে COD হবে?"],
      ["mitu", "জি, L আছে। ঢাকার বাইরে ডেলিভারি ৳১৩০, ক্যাশ অন ডেলিভারি করা যাবে। মোট ৳১,৫৮০। অর্ডার কনফার্ম করব?"],
      ["them", "হ্যাঁ"],
      ["mitu", "হয়ে গেছে ✓ অর্ডার #১০৪২ কনফার্ম। পাঠানোর সময় আপনাকে জানিয়ে দেব।"],
    ],
    floats: [[1, "⚡", "২ সেকেন্ডে উত্তর", "right"], [5, "✓", "অর্ডার #১০৪২ · ৳১,৫৮০", "left"]],
    end: [[{ text: "সব মেসেজের উত্তর।" }], [{ text: "সব অর্ডার কনফার্ম।", accent: true }]],
    endSub: "মেসেজ সামলাক মিতু। আপনি অর্ডার প্যাক করুন।",
    channels: ["হোয়াটসঅ্যাপ", "মেসেঞ্জার", "ইনস্টাগ্রাম", "SMS", "ফোন কল"],
  },
  photo: {
    lang: "en", shop: "Nakshi Threads", clock: "11:52", online: "online", typing: "typing…", message: "Message", today: "Today",
    hook: [[{ text: "Typing the same price" }], [{ text: "200 times a day?", accent: true }]],
    chips: ["price?", "price?", "how much?", "price pls", "price?", "how much is this one? 📷", "price??", "rate?",
      "price?", "how much?", "price", "price?", "dam koto?", "price?"],
    kicker: "Let Mitu answer",
    lines: [
      ["them", "how much is this one?", "photo"],
      ["mitu", "That’s the Mustard Embroidered Kurti, ৳1,650. Only 3 left! Which size?"],
      ["them", "M. delivery charge outside dhaka?"],
      ["mitu", "৳130 by courier, 2–4 days. Cash on delivery or bKash. Total ৳1,780. Confirm?"],
      ["them", "bkash. confirm"],
      ["mitu", "Order #1043 placed ✓ Send ৳1,780 to 01700-000000 and reply with the transaction ID."],
    ],
    floats: [[1, "📷", "Knew the post from a screenshot", "right"], [5, "📦", "New order #1043 · ৳1,780", "left"], [5, "↓", "Stock: 3 → 2 left", "right"]],
    end: [[{ text: "It reads the screenshot." }], [{ text: "It takes the order.", accent: true }]],
    endSub: "Facebook, Instagram and WhatsApp shops, day and night.",
    channels: ["WhatsApp", "Messenger", "Instagram", "SMS", "Calls"],
  },
  cafe: {
    lang: "en", shop: "Little Fern Café", clock: "8:12", online: "online", typing: "typing…", message: "Message", today: "Today",
    hook: [[{ text: "Your barista can't" }], [{ text: "pour and text.", accent: true }]],
    chips: ["two flat whites?", "oat milk?", "open now?", "is the risotto gluten free?", "🎤 voice note", "pickup in 15?",
      "any vegan options?", "large latte pls", "what time do you close?", "can I order ahead?", "decaf?", "banana bread left?", "🎤 voice note", "open now?"],
    kicker: "Mitu takes the orders",
    lines: [
      ["them", "0:05", "voice", "voices/cafe1.wav", 5.01],
      ["mitu", "Heard: “two flat whites, one with oat, for pickup.” Regular size? That’s $10.80, ready in 15 min."],
      ["them", "yes please!"],
      ["mitu", "Order #87 confirmed ✓ Two flat whites, one oat, ready at the counter in 15 minutes."],
      ["them", "is the risotto gluten free?"],
      ["mitu", "The Mushroom Risotto has no gluten ingredients, but our kitchen handles flour, so I can’t promise it’s safe for coeliacs."],
    ],
    floats: [[1, "🎤", "Ordered by voice note", "right"], [3, "☕", "Kitchen · 2 × Flat White", "left"], [5, "!", "Honest about allergens", "right"]],
    end: [[{ text: "Orders in." }], [{ text: "Coffee out.", accent: true }]],
    endSub: "Let Mitu take the orders. You make the coffee.",
    channels: ["WhatsApp", "Messenger", "Instagram", "SMS", "Calls"],
  },
  voice: {
    lang: "en", shop: "Nakshi Threads", clock: "9:26", online: "online", typing: "typing…", message: "Message", today: "Today",
    hook: [[{ text: "Your customers" }], [{ text: "don't type.", accent: true }]],
    chips: ["🎤 0:06", "🎤 0:12", "🎤 0:03", "🎤 0:21", "🎤 0:08", "🎤 0:04", "🎤 0:15", "🎤 0:09", "🎤 0:02", "🎤 0:11",
      "🎤 0:07", "🎤 0:05", "🎤 0:18", "🎤 0:06"],
    kicker: "Mitu listens",
    lines: [
      ["them", "0:06", "voice", "voices/shop1.wav", 6.2],
      ["mitu", "Heard: “Do you have the indigo kurti in L? How much to Chittagong?” Yes, L is in stock, ৳1,450. Delivery outside Dhaka is ৳130, so ৳1,580 in total. Shall I place it?"],
      ["them", "0:02", "voice", "voices/shop2.wav", 2.11],
      ["mitu", "Heard: “Yes, cash on delivery.” Done ✓ Order #1044 is placed. We’ll message you when it ships."],
    ],
    floats: [[1, "🎤", "Understood a voice note", "right"], [3, "✓", "Order #1044 · ৳1,580", "left"]],
    end: [[{ text: "Talk or type." }], [{ text: "Mitu takes the order.", accent: true }]],
    endSub: "Voice notes in English or Bangla, answered in seconds.",
    channels: ["WhatsApp", "Messenger", "Instagram", "SMS", "Calls"],
  },
};

export const HOOK_OUT = 2.8; // the phone arrives
const FIRST = HOOK_OUT + 0.7;

// When each line lands, when Mitu's typing starts, and when the end card comes in.
export function timeline(r) {
  let cur = FIRST;
  const at = [], typing = [];
  for (const [who, text, kind, , len] of r.lines) {
    const n = kind === "voice" ? 20 : [...text].length;
    if (who === "mitu") {
      typing.push([cur, cur + 0.9]);
      at.push(cur + 0.9);
      cur += 0.9 + 1.0 + 0.034 * n;
    } else {
      at.push(cur);
      if (len) { cur += 0.3 + len + 0.2; continue; } // a voice note with sound: Mitu waits for it to finish
      cur += Math.max(1.0, 0.7 + 0.02 * n) + (kind === "photo" ? 0.6 : 0);
    }
  }
  const endAt = cur + 0.6;
  return { at, typing, endAt, duration: +(endAt + 4.2).toFixed(2) };
}

if (typeof process !== "undefined" && process.argv[1]?.endsWith("mitu_data.js")) {
  for (const [k, r] of Object.entries(REELS)) console.log(k, timeline(r).duration);
}
