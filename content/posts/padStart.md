---
title: "padStart & padEnd"
date: 2019-01-01T00:00:00+08:00
slug: "padStart"
url: "/padStart.html"
categories:
  - "归档"
  - "javascript"
tags:
  - "es6+"
  - "javascript"
hiddenFromHomePage: true
---

在ES8中，为String新增 padStart & padEnd， 用来填充字符串。

#### 1.使用场景

- 生成统一位数的文件名、编号等；eg：0001.txt ～ 9999.txt
- 带有统一前缀或后缀的字符串、名字、编码等；eg：¥1,000.00，#EFEFEF，0x001F
- 生成位数一样的字符串，以便打印和显示。

---
#### 2.语法
**str.padStart(targetLength [, padString])**

---
#### 3.参数

**targetLength**

当前字符串需要填充到的目标长度。如果这个数值小于当前字符串的长度，则返回当前字符串本身。

**padString 可选**

填充字符串。如果字符串太长，使填充后的字符串长度超过了目标长度，则只保留最左侧的部分，其他部分会被截断。此参数的缺省值为 " "（U+0020）。

---
4.返回值

在原字符串开头填充指定的填充字符串直到目标长度所形成的新字符串

---
5.示例

```javascript
'abc'.padStart(10); // " abc"

'abc'.padStart(10, "foo"); // "foofoofabc"

'abc'.padStart(6,"123465"); // "123abc"

'abc'.padStart(8, "0"); // "00000abc"

'abc'.padStart(1); // "abc"
```

---
6.源代码（polyfill 方法)

```javascript
if (!String.prototype.padStart) {
  String.prototype.padStart = function padStart(targetLength,padString) {
    targetLength = targetLength>>0; //floor if number or convert non-number to 0;
    padString = String((typeof padString !== 'undefined' ? padString : ''));

    if (this.length > targetLength) {
      return String(this);
    }
    else {
      targetLength = targetLength–this.length;
      if (targetLength > padString.length) {
      //append to original to ensure we are longer than needed
        padString += padString.repeat(targetLength/padString.length); 
      }
    return padString.slice(0,targetLength) + String(this);
    }
  };
}
```

padEnd 同理。 也可以用 lodash 相应的 padStart 和 padEnd 代替
