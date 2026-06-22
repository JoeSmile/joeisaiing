---
title: "vue key有个坑"
date: 2019-08-21T12:16:45+08:00
categories:
  - "归档"
slug: "vue-key"
url: "/vue-key.html"
tags:
  - "vue"
  - "key"
hiddenFromHomePage: true
---

在vue2.x 中，我们经常使用key来提高组件性能，给了 input  或者 在 v-for 中 给子组件/元素一个 key 来加速diff渲染，这也是官方推荐的做法。不过 key 的赋值还真的不能马虎。

#### 案例1. 无key的情况，切换 input 无法自动清空

在 input 不加 key 的时候，切换这两个 input 标签，input 框框里的值不会变
![](vue-key/vuekey1.png)

#### 案例2. key相同tag标签，多次出现在同一个页面

这个bug很少见，但见了后会很头疼。通常我们使用key 偷懒的情况使用index来做key，
```js
<div v-for="(item, index) in list" :key="index" />
```
 这样的key写多了，又同时进行渲染，在来个排序什么的，就很容易出现bug。最好 key + 时间戳 或者 使用唯一的key标示。

**总结： key 要唯一 ！要唯一！要唯一!**

---

另外一个渲染 input radio 显示不正确的问题

![](vue-key/vuekey2.png)


在以上代码，原本想点击Add one 渲染多个inputRadio 组件，从而进行Yes or No的选择。但以上有2个错误。

**错误1. 在组件内部 id 不唯一。 在多次进行inputRadio时候会渲染多个id为yes 和 no的input组件。从而使label总绑定到第一个input上。**

**错误2. 在input中使用name时候，名字一样， 导致多次渲染inputRadio时候无法准确定位input。**

正确代码可以将 id 和 name 加上时间戳编程唯一的 id / name。
