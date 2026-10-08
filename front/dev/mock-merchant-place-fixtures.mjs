// Fictional development data, never Google response content.
export const mockMerchantPlace={provider:'google',placeId:'mock-fictional-store',method:'google_selected'};
export function mockPlaceDetails(id){return id===mockMerchantPlace.placeId?{placeId:id,name:'架空ストア',address:'架空県サンプル市1-2-3',googleMapsUri:'https://maps.google.com/',attributions:[],provider:'google'}:null;}
export function retainMockMerchantPlace(old,next){return next.type==='expense'&&next.merchant===old.merchant&&(next.merchantAddress??null)===(old.merchantAddress??null)?old.merchantPlace:undefined;}
