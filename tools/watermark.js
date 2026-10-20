// 캡처 요소(data-out) 우측 하단에 @NTL 워터마크. bg*.png(배경 소스)는 제외.
document.querySelectorAll('[data-out]').forEach(el=>{
  if(/^bg\d/.test(el.dataset.out)) return;
  if(getComputedStyle(el).position==='static') el.style.position='relative';
  const m=getComputedStyle(el).backgroundColor.match(/\d+/g)||[255,255,255];
  const opaque=m.length<4||+m[3]>0;  // 투명 배경(SVG로 칠한 캔버스)은 data-wm으로 지정
  const light=el.dataset.wm==='dark'||(opaque&&(0.299*m[0]+0.587*m[1]+0.114*m[2])>150);
  el.insertAdjacentHTML('beforeend','<div class="wm"'+(light?' style="color:rgba(17,17,17,.75);text-shadow:none"':'')+'>@NTL</div>');
});
